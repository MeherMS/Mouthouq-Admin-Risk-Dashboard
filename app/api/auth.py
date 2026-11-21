"""Shared API key. Every endpoint requires X-API-Key, except /health.

Fails closed: if API_KEY is not set on the server, protected endpoints refuse requests.
Applied to every route through FastAPI(dependencies=[...]) in main.py.
"""
import os
import secrets

from fastapi import HTTPException, Request

API_KEY_HEADER = "X-API-Key"
EXEMPT_PATHS = {"/health"}


def require_api_key(request: Request) -> None:
    if request.url.path in EXEMPT_PATHS:
        return
    expected = os.environ.get("API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured on the server")
    provided = request.headers.get(API_KEY_HEADER, "")
    if not secrets.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")