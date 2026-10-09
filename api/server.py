import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request, Depends, Response, Query
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import validate, ValidationError
from pydantic import BaseModel
from adapters.python_adapter import PythonAdapter
from adapters.catala_adapter import CatalaAdapter
from catalog.manifest_loader import enrich_with_pyproject_text, flatten_package_manifest
from catalog.jsonld_converter import manifest_to_jsonld
from user.fc_mapping import FCMappingEngine, get_fc_mapping_engine


AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")

app = FastAPI(title="Datapi POC")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/admin", StaticFiles(directory=STATIC_DIR, html=True), name="admin")

# Mount user static files
USER_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "user")
if os.path.exists(USER_STATIC_DIR):
    app.mount("/user/static", StaticFiles(directory=USER_STATIC_DIR, html=True), name="user_static")

# Adapter registry: dispatch execution based on manifest.runtime.language.
ADAPTERS = {
    "python": PythonAdapter,
    "catala": CatalaAdapter,
}

# Simple in-memory manifest store for POC (replace with Postgres for prod)
MANIFEST_STORE = {}

# ============================================================================
# FRANCE CONNECT INTEGRATION
# ============================================================================

# In-memory stores for POC (replace with database for production)
FC_SESSION_STORE: Dict[str, Dict[str, Any]] = {}  # session_id -> session_data
FC_USER_STORE: Dict[str, Dict[str, Any]] = {}  # user_id (sub) -> user_data + consent

# France Connect configuration
FC_CONFIG = {
    "authorization_url": os.getenv(
        "FC_AUTHORIZATION_URL",
        "ttps://fcp-low.sbx.dev-franceconnect.fr/api/v2/authorize"
    ),
    "token_url": os.getenv(
        "FC_TOKEN_URL",
        "https://fcp-low.sbx.dev-franceconnect.fr/api/v2/token"
    ),
    "userinfo_url": os.getenv(
        "FC_USERINFO_URL",
        "https://fcp-low.sbx.dev-franceconnect.fr/api/v2/userinfo"
    ),
    "client_id": os.getenv("FRANCECONNECT_CLIENT_ID", ""),
    "client_secret": os.getenv("FRANCECONNECT_CLIENT_SECRET", ""),
    "redirect_uri": os.getenv(
        "FC_REDIRECT_URI",
        "http://localhost:8000/user/auth/fc/callback"
    ),
    "scopes": ["openid", "profile", "email", "address", "phone"],
}

# Session configuration
SESSION_CONFIG = {
    "cookie_name": "datapi_fc_session",
    "cookie_max_age": 3600,  # 1 hour
    "cookie_secure": os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    "cookie_httponly": True,
}

# Get FC mapping engine instance
fc_mapping_engine = get_fc_mapping_engine()


class FCSessionData(BaseModel):
    """France Connect session data."""
    session_id: str
    user_id: str  # FC sub claim
    access_token: str
    id_token: str
    claims: Dict[str, Any]
    created_at: datetime
    expires_at: datetime
    consent: Dict[str, bool]  # Field path -> consent boolean


class UserConsent(BaseModel):
    """User consent for data sharing with algorithms."""
    algorithm_id: str
    consented_fields: List[str]  # List of field paths user has consented to
    consented_at: datetime
    

class UserPivotData(BaseModel):
    """Pivot data for a user (extracted from FC claims)."""
    user_id: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    full_name: Optional[str] = None
    birthdate: Optional[str] = None
    age: Optional[int] = None
    email: Optional[str] = None
    postal_code: Optional[str] = None
    department: Optional[str] = None
    city: Optional[str] = None
    identity_provider: Optional[str] = None
    
    @classmethod
    def from_fc_claims(cls, user_id: str, claims: Dict[str, Any]) -> "UserPivotData":
        """Create pivot data from FC claims using the mapping engine."""
        pivot_data = fc_mapping_engine.extract_pivot_data(claims)
        return cls(
            user_id=user_id,
            given_name=pivot_data.get("given_name"),
            family_name=pivot_data.get("family_name"),
            full_name=pivot_data.get("full_name"),
            birthdate=pivot_data.get("birthdate"),
            age=pivot_data.get("age"),
            email=pivot_data.get("email"),
            postal_code=pivot_data.get("postal_code"),
            department=pivot_data.get("department"),
            city=pivot_data.get("city"),
            identity_provider=pivot_data.get("identity_provider")
        )


def generate_session_id() -> str:
    """Generate a secure session ID."""
    return secrets.token_urlsafe(32)


def generate_state() -> str:
    """Generate a CSRF state token."""
    return secrets.token_urlsafe(16)


def get_session_from_cookie(request: Request) -> Optional[Dict[str, Any]]:
    """Get FC session from request cookie."""
    session_id = request.cookies.get(SESSION_CONFIG["cookie_name"])
    if not session_id:
        return None
    return FC_SESSION_STORE.get(session_id)


def get_user_from_session(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get user data from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return FC_USER_STORE.get(user_id)


def require_user_session(request: Request) -> Dict[str, Any]:
    """Dependency to require a valid user session."""
    session = get_session_from_cookie(request)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please log in via France Connect."
        )
    
    # Check if session is expired
    expires_at = session.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please log in again."
        )
    
    return session

def require_auth(authorization: str | None = Header(default=None)):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    if token != AUTH_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return token

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/manifest-schema")
def manifest_schema():
    # served for the /admin console's client-side manifest validation helper
    schema_path = os.path.join(os.path.dirname(__file__), "..", "catalog", "manifest.schema.json")
    with open(schema_path) as f:
        return json.load(f)

@app.post("/catalog/infer-schema")
def infer_schema(entrypoint: dict, token: str = Depends(require_auth)):
    # helper for the /admin console: generate input_schema/output_schema from the
    # compiled Catala module's own type hints, instead of hand-transcribing them.
    if entrypoint.get("type") != "catala:scope":
        raise HTTPException(status_code=400, detail="schema inference only supported for entrypoint.type 'catala:scope'")
    target = entrypoint.get("target")
    if not target:
        raise HTTPException(status_code=400, detail="entrypoint.target required")
    try:
        return CatalaAdapter().infer_manifest_schemas(target)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/catalog/enrich-from-pyproject")
def enrich_from_pyproject(body: dict, token: str = Depends(require_auth)):
    # helper for the /admin console: fill manifest.name/version/description/license/tags
    # from a pyproject.toml's [project] table, mirroring catalog.manifest_loader.load_manifest
    # for the manual-paste flow where there's no manifest.json file path to look next to.
    manifest = body.get("manifest")
    pyproject_toml = body.get("pyproject_toml")
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="body.manifest (object) required")
    if not isinstance(pyproject_toml, str) or not pyproject_toml.strip():
        raise HTTPException(status_code=400, detail="body.pyproject_toml (non-empty string) required")
    try:
        return enrich_with_pyproject_text(manifest, pyproject_toml)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid pyproject.toml: {e}")

@app.post("/catalog/register")
def register_manifest(manifest: dict, token: str = Depends(require_auth)):
    if "algorithms" in manifest:
        entries = flatten_package_manifest(manifest)
        ids = []
        for entry in entries:
            if "id" not in entry:
                raise HTTPException(status_code=400, detail="each algorithms[] entry requires id")
            MANIFEST_STORE[entry["id"]] = entry
            ids.append(entry["id"])
        return {"status": "registered", "ids": ids}
    if "id" not in manifest:
        raise HTTPException(status_code=400, detail="manifest.id required")
    MANIFEST_STORE[manifest["id"]] = manifest
    return {"status": "registered", "id": manifest["id"]}

@app.get("/catalog/{manifest_id}")
def get_manifest(manifest_id: str, token: str = Depends(require_auth)):
    m = MANIFEST_STORE.get(manifest_id)
    if not m:
        raise HTTPException(status_code=404, detail="manifest not found")
    return m

@app.get("/catalog/{manifest_id}/metadata.jsonld")
def manifest_metadata_jsonld(manifest_id: str, token: str = Depends(require_auth)):
    # generates a single-service metadata.jsonld from the already-flattened
    # stored entry -- reconstructing the original package's multi-service
    # grouping at export time is future work, out of scope here.
    m = MANIFEST_STORE.get(manifest_id)
    if not m:
        raise HTTPException(status_code=404, detail="manifest not found")
    return manifest_to_jsonld(m)

# List manifest ids in the store
@app.get("/catalog")
def get_manifest(token: str = Depends(require_auth)):
    return list(MANIFEST_STORE.keys())

# lightweight input validation + execution dispatch
@app.post("/execute/{manifest_id}")
async def execute(manifest_id: str, request: Request, token: str = Depends(require_auth)):
    manifest = MANIFEST_STORE.get(manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="manifest not found")
    body = await request.json()
    # validate input_schema
    try:
        validate(instance=body, schema=manifest["input_schema"])
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"input validation error: {e.message}")
    resources = manifest.get("resources", {})
    timeout = resources.get("timeout_seconds", 30)
    run_id = str(uuid.uuid4())
    language = manifest.get("runtime", {}).get("language")
    adapter_cls = ADAPTERS.get(language)
    if adapter_cls is None:
        raise HTTPException(status_code=400, detail=f"unsupported runtime.language '{language}'")
    result = adapter_cls().execute_sync(manifest, run_id, body, exec_opts={"timeout_seconds": timeout})
    return JSONResponse(status_code=200, content=result)


# ============================================================================
# FRANCE CONNECT AUTHENTICATION ENDPOINTS
# ============================================================================

@app.get("/user/auth/fc/login")
def fc_login(request: Request):
    """
    Initiate France Connect login flow.
    Redirects the user to France Connect authorization endpoint.
    """
    # Generate state token for CSRF protection
    state = generate_state()
    
    # Store state in session (simplified for POC - in prod, use proper session store)
    # For now, we'll pass it as a query parameter and verify in callback
    
    # Build authorization URL
    auth_url = FC_CONFIG["authorization_url"]
    params = {
        "client_id": FC_CONFIG["client_id"],
        "redirect_uri": FC_CONFIG["redirect_uri"],
        "scope": " ".join(FC_CONFIG["scopes"]),
        "response_type": "code",
        "state": state,
        "nonce": generate_state(),  # For replay protection
        "acr_values": "eidas1",  # Level of assurance
    }
    
    # Construct query string
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    
    return RedirectResponse(url=f"{auth_url}?{query_string}")


@app.get("/user/auth/fc/callback")
async def fc_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None)
):
    """
    France Connect callback endpoint.
    Exchanges the authorization code for an access token and retrieves user info.
    """
    if error:
        return JSONResponse(
            status_code=400,
            content={"error": error, "error_description": error_description}
        )
    
    # TODO: Validate state token (CSRF protection) - for POC, we skip
    
    # Exchange code for token
    try:
        # For POC/simplification, we'll mock the token exchange
        # In production, use proper OAuth2 client
        # This is a placeholder for the actual implementation
        
        # Mock: In integration mode, we can use a test token
        # For now, we'll simulate getting user info
        # In real implementation, you would:
        # 1. POST to token_url with code, client_id, client_secret, redirect_uri
        # 2. Get access_token and id_token
        # 3. Validate id_token signature
        # 4. GET userinfo with access_token
        
        # For POC, let's create a mock user response
        # In real use, this would come from FC userinfo endpoint
        mock_claims = {
            "sub": f"user_{secrets.token_hex(8)}",
            "given_name": "Test",
            "family_name": "User",
            "birthdate": "1990-01-01",
            "email": "test.user@example.com",
            "gender": "male",
            "address": {
                "postal_code": "75001",
                "city": "Paris",
                "formatted": "1 Rue de Paris, 75001 Paris",
                "country": "FR"
            },
            "phone": "+33123456789",
            "identity_provider": "fi",
            "identity_level": "substantial",
            "amr": ["pwd"],
        }
        
        # Create session
        session_id = generate_session_id()
        now = datetime.now()
        expires_at = now + timedelta(seconds=SESSION_CONFIG["cookie_max_age"])
        
        session_data = {
            "session_id": session_id,
            "user_id": mock_claims["sub"],
            "access_token": f"mock_token_{secrets.token_hex(16)}",
            "id_token": f"mock_id_token_{secrets.token_hex(16)}",
            "claims": mock_claims,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "consent": {}  # Empty consent initially
        }
        
        # Store session
        FC_SESSION_STORE[session_id] = session_data
        
        # Create/Update user in store
        user_data = {
            "user_id": mock_claims["sub"],
            "created_at": now.isoformat(),
            "last_login": now.isoformat(),
            "fc_claims": mock_claims,
            "consent": {}  # Will be populated as user consents to algorithms
        }
        FC_USER_STORE[mock_claims["sub"]] = user_data
        
        # Set cookie
        response = RedirectResponse(url="/user/algorithms")
        response.set_cookie(
            key=SESSION_CONFIG["cookie_name"],
            value=session_id,
            max_age=SESSION_CONFIG["cookie_max_age"],
            httponly=SESSION_CONFIG["cookie_httponly"],
            secure=SESSION_CONFIG["cookie_secure"],
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"France Connect authentication failed: {str(e)}"
        )


@app.get("/user/logout")
def logout(response: Response, request: Request):
    """Logout and clear session."""
    session_id = request.cookies.get(SESSION_CONFIG["cookie_name"])
    if session_id and session_id in FC_SESSION_STORE:
        del FC_SESSION_STORE[session_id]
    
    # Clear cookie
    response.delete_cookie(SESSION_CONFIG["cookie_name"])
    return RedirectResponse(url="/user/login")


# ============================================================================
# USER DATA ENDPOINTS
# ============================================================================

@app.get("/user/pivot")
def get_user_pivot(session: Dict[str, Any] = Depends(require_user_session)):
    """
    Get the pivot data for the current user.
    Pivot data are the core attributes extracted from FC claims.
    """
    claims = session.get("claims", {})
    pivot_data = fc_mapping_engine.extract_pivot_data(claims)
    
    return {
        "status": "ok",
        "pivot_data": pivot_data
    }


@app.get("/user/catalog")
def get_user_catalog(session: Dict[str, Any] = Depends(require_user_session)):
    """
    List all published algorithms in the catalog.
    For user interface, we return manifests with their FC mapping info.
    """
    manifest_ids = list(MANIFEST_STORE.keys())
    
    # Get user's consent for each algorithm
    user_id = session.get("user_id")
    user_data = FC_USER_STORE.get(user_id, {})
    user_consent = user_data.get("consent", {})
    
    catalog = []
    for manifest_id in manifest_ids:
        manifest = MANIFEST_STORE[manifest_id]
        
        # Check if algorithm has FC mapping
        has_fc_mapping = "franceconnect_mapping" in manifest
        
        # Check user consent for this algorithm
        algo_consent = user_consent.get(manifest_id, {})
        
        catalog.append({
            "id": manifest_id,
            "title": manifest.get("dct:title", manifest_id),
            "description": manifest.get("description", ""),
            "org": manifest.get("org", ""),
            "version": manifest.get("version", ""),
            "tags": manifest.get("tags", []),
            "has_fc_mapping": has_fc_mapping,
            "consent_given": bool(algo_consent)
        })
    
    return {
        "status": "ok",
        "algorithms": catalog
    }


@app.get("/user/catalog/{manifest_id}")
def get_user_manifest(
    manifest_id: str,
    session: Dict[str, Any] = Depends(require_user_session)
):
    """
    Get a specific manifest with FC mapping information for the user.
    """
    manifest = MANIFEST_STORE.get(manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Algorithm not found")
    
    # Get user's FC claims
    claims = session.get("claims", {})
    
    # Get field metadata using the mapping engine
    field_metadata = fc_mapping_engine.get_field_metadata(claims, manifest)
    
    # Check user consent for this algorithm
    user_id = session.get("user_id")
    user_data = FC_USER_STORE.get(user_id, {})
    user_consent = user_data.get("consent", {}).get(manifest_id, {})
    
    # Add consent status to each field
    for field in field_metadata:
        field_path = field["path"]
        field["consented"] = user_consent.get(field_path, False)
    
    return {
        "status": "ok",
        "manifest": manifest,
        "field_metadata": field_metadata,
        "consent": user_consent
    }


@app.post("/user/consent")
async def update_user_consent(
    request: Request,
    session: Dict[str, Any] = Depends(require_user_session)
):
    """
    Update user consent for algorithm fields.
    Called when user accepts/rejects sharing specific FC data with an algorithm.
    """
    body = await request.json()
    
    algorithm_id = body.get("algorithm_id")
    if not algorithm_id:
        raise HTTPException(status_code=400, detail="algorithm_id required")
    
    consent_updates = body.get("consent", {})
    if not isinstance(consent_updates, dict):
        raise HTTPException(status_code=400, detail="consent must be an object")
    
    # Get user data
    user_id = session.get("user_id")
    user_data = FC_USER_STORE.get(user_id, {})
    
    # Initialize consent for this user if not exists
    if "consent" not in user_data:
        user_data["consent"] = {}
    
    # Initialize consent for this algorithm if not exists
    if algorithm_id not in user_data["consent"]:
        user_data["consent"][algorithm_id] = {}
    
    # Update consent for each field
    for field_path, consent_value in consent_updates.items():
        if isinstance(consent_value, bool):
            user_data["consent"][algorithm_id][field_path] = consent_value
    
    # Update session consent as well
    if "consent" not in session:
        session["consent"] = {}
    session["consent"][algorithm_id] = user_data["consent"][algorithm_id]
    
    return {
        "status": "ok",
        "consent": user_data["consent"][algorithm_id]
    }


@app.post("/user/execute/{manifest_id}")
async def user_execute(
    manifest_id: str,
    request: Request,
    session: Dict[str, Any] = Depends(require_user_session)
):
    """
    Execute an algorithm with user data (FC + manual inputs).
    
    This endpoint:
    1. Gets the manifest
    2. Applies FC mapping to pre-fill data
    3. Merges with user-provided data
    4. Validates against input_schema
    5. Executes the algorithm
    """
    manifest = MANIFEST_STORE.get(manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Algorithm not found")
    
    # Get user's FC claims
    claims = session.get("claims", {})
    
    # Get user consent for this algorithm
    user_id = session.get("user_id")
    user_data = FC_USER_STORE.get(user_id, {})
    user_consent = user_data.get("consent", {}).get(manifest_id, {})
    
    # Get user-provided input data from request
    body = await request.json()
    user_input = body.get("input", {})
    
    # Generate base payload from FC data
    input_payload, missing_fields, consent_fields = fc_mapping_engine.generate_input_payload(
        claims, manifest, user_consent
    )
    
    # Merge with user-provided data
    # User data takes precedence over FC data
    def deep_merge(base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries, with override taking precedence."""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    final_input = deep_merge(input_payload, user_input)
    
    # Validate against input schema
    try:
        validate(instance=final_input, schema=manifest["input_schema"])
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Input validation error: {e.message}")
    
    # Execute the algorithm
    resources = manifest.get("resources", {})
    timeout = resources.get("timeout_seconds", 30)
    run_id = str(uuid.uuid4())
    language = manifest.get("runtime", {}).get("language")
    adapter_cls = ADAPTERS.get(language)
    
    if adapter_cls is None:
        raise HTTPException(status_code=400, detail=f"Unsupported runtime.language '{language}'")
    
    # Log execution with user context
    execution_context = {
        "run_id": run_id,
        "manifest_id": manifest_id,
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
        "input": final_input
    }
    
    result = adapter_cls().execute_sync(
        manifest, 
        run_id, 
        final_input, 
        exec_opts={"timeout_seconds": timeout}
    )
    
    # Add execution context to result
    result["execution_context"] = execution_context
    
    return JSONResponse(status_code=200, content=result)


# ============================================================================
# USER PAGES (HTML)
# ============================================================================

@app.get("/user/login")
def user_login_page():
    """Serve the France Connect login page."""
    return HTMLResponse(content=open(
        os.path.join(USER_STATIC_DIR, "login.html"), "r"
    ).read())


@app.get("/user/algorithms")
def user_algorithms_page(session: Dict[str, Any] = Depends(require_user_session)):
    """Serve the 'Mes algorithmes publics' page."""
    return HTMLResponse(content=open(
        os.path.join(USER_STATIC_DIR, "algorithms.html"), "r"
    ).read())


@app.get("/user/execute/{manifest_id}")
def user_execute_page(
    manifest_id: str,
    session: Dict[str, Any] = Depends(require_user_session)
):
    """Serve the algorithm execution page."""
    # Verify manifest exists
    manifest = MANIFEST_STORE.get(manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Algorithm not found")
    
    return HTMLResponse(content=open(
        os.path.join(USER_STATIC_DIR, "execute.html"), "r"
    ).read())


if __name__ == "__main__":
    import uvicorn # debugging
    uvicorn.run(app, host="0.0.0.0", port=8000)