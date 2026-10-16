import httpx
import base64
import json as _json

class FCClientError(Exception):
    """France Connect HTTP call failed."""

async def exchange_code(config: dict, code: str) -> dict:
    """Exchange an OAuth2 authorization code for tokens at the FC token endpoint."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(config["token_url"], data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": config["redirect_uri"],
        })
    if resp.status_code != 200:
        raise FCClientError(f"token exchange failed: {resp.status_code} {resp.text}")
    return resp.json()

def _decode_jwt_payload(jwt: str) -> dict:
    payload_b64 = jwt.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)  # re-remplit le padding base64url
    return _json.loads(base64.urlsafe_b64decode(payload_b64))

async def fetch_userinfo(config: dict, access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            config["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
    print("userinfo status:", resp.status_code,
          "| content-type:", resp.headers.get("content-type"),
          "| body:", resp.text[:500])
    if resp.status_code != 200:
        raise FCClientError(f"userinfo failed: {resp.status_code} {resp.text}")
    if resp.headers.get("content-type", "").startswith("application/jwt"):
        # TODO (prod): vérifier la signature JWS (ES256, kid "pkcs11:ES256:hsm")
        # contre la JWKS FC avant de faire confiance aux claims
        return _decode_jwt_payload(resp.text)
    return resp.json()