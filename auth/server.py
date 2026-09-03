from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse
import os

app = FastAPI(title="Auth Mock")

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")

@app.post("/token")
def token(grant_type: str = Form(...), client_id: str = Form(None), client_secret: str = Form(None)):
    # accept client_credentials and return static token (POC)
    if grant_type != "client_credentials":
        return JSONResponse(status_code=400, content={"error": "unsupported_grant_type"})
    return {"access_token": AUTH_TOKEN, "token_type": "bearer", "expires_in": 3600}
