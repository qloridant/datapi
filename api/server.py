import os
import uuid
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.responses import JSONResponse
from jsonschema import validate as js_validate, ValidationError
from adapters.python_adapter import PythonAdapter
from adapters.catala_adapter import CatalaAdapter


AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")

app = FastAPI(title="Datapi POC")

# Adapter registry: dispatch execution based on manifest.runtime.language.
ADAPTERS = {
    "python": PythonAdapter,
    "catala": CatalaAdapter,
}

# Simple in-memory manifest store for POC (replace with Postgres for prod)
MANIFEST_STORE = {}

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

@app.post("/catalog/register")
def register_manifest(manifest: dict, token: str = Depends(require_auth)):
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
        js_validate(instance=body, schema=manifest["input_schema"])
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

if __name__ == "__main__":
    import uvicorn # debugging
    uvicorn.run(app, host="0.0.0.0", port=8000)