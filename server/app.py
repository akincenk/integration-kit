"""Reference verification API used to practise customer integrations.

It behaves like a small identity-verification service: API-key auth, idempotent creates,
rate limiting with Retry-After, structured errors with request ids, and signed webhooks.
State is in memory on purpose: the point is the integration contract, not storage.
"""

import hashlib
import hmac
import json
import os
import threading
import time
import uuid

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

API_KEYS = set(filter(None, os.environ.get("IK_API_KEYS", "sk_test_demo").split(",")))
WEBHOOK_SECRET = os.environ.get("IK_WEBHOOK_SECRET", "whsec_demo")
RATE_PER_MINUTE = int(os.environ.get("IK_RATE_PER_MINUTE", "60"))
CHECKS = {"age_over_18", "age_over_21", "document", "liveness"}

app = FastAPI(title="Integration Kit reference API", version="1.0.0")
_lock = threading.Lock()
_verifications: dict[str, dict] = {}
_idempotency: dict[tuple[str, str], tuple[str, str]] = {}  # (key, idem) -> (body hash, verification id)
_buckets: dict[str, list[float]] = {}


class VerificationIn(BaseModel):
    user_ref: str = Field(min_length=1, max_length=128)
    checks: list[str] = Field(min_length=1)


def error(status: int, code: str, message: str, request_id: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, headers={"X-Request-Id": request_id, **(headers or {})},
                        content={"error": {"code": code, "message": message, "request_id": request_id}})


def sign(payload: bytes, secret: str, ts: int) -> str:
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _status(v: dict) -> dict:
    # Deterministic outcome so integrations can be tested: user_ref starting with "fail" is rejected.
    if v["status"] == "pending" and time.time() - v["created_at"] >= 1.0:
        v["status"] = "rejected" if v["user_ref"].startswith("fail") else "verified"
    return {k: v[k] for k in ("id", "user_ref", "checks", "status", "created_at")}


@app.middleware("http")
async def request_id_and_auth(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:16]}"
    request.state.rid = rid
    if request.url.path.startswith("/v1/"):
        auth = request.headers.get("Authorization", "")
        key = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if key not in API_KEYS:
            return error(401, "invalid_api_key", "Send 'Authorization: Bearer <api key>'.", rid)
        now = time.time()
        with _lock:
            hits = [t for t in _buckets.get(key, []) if now - t < 60]
            if len(hits) >= RATE_PER_MINUTE:
                retry = max(1, int(60 - (now - hits[0])) + 1)
                return error(429, "rate_limited", "Too many requests.", rid, {"Retry-After": str(retry)})
            hits.append(now)
            _buckets[key] = hits
        request.state.key = key
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz():
    return {"ready": True, "api_keys": len(API_KEYS)}


@app.post("/v1/verifications", status_code=201)
def create_verification(body: VerificationIn, request: Request, idempotency_key: str | None = Header(default=None)):
    rid = request.state.rid
    unknown = sorted(set(body.checks) - CHECKS)
    if unknown:
        return error(422, "unknown_check", f"Unknown checks: {', '.join(unknown)}. Allowed: {', '.join(sorted(CHECKS))}.", rid)
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    with _lock:
        if idempotency_key:
            prev = _idempotency.get((request.state.key, idempotency_key))
            if prev:
                if prev[0] != digest:
                    return error(409, "idempotency_conflict", "This Idempotency-Key was used with a different body.", rid)
                return JSONResponse(status_code=200, content=_status(_verifications[prev[1]]))
        vid = f"ver_{uuid.uuid4().hex[:20]}"
        _verifications[vid] = {"id": vid, "user_ref": body.user_ref, "checks": body.checks,
                               "status": "pending", "created_at": time.time()}
        if idempotency_key:
            _idempotency[(request.state.key, idempotency_key)] = (digest, vid)
        return _status(_verifications[vid])


@app.get("/v1/verifications/{vid}")
def get_verification(vid: str, request: Request):
    with _lock:
        v = _verifications.get(vid)
        if not v:
            return error(404, "not_found", f"No verification {vid}.", request.state.rid)
        return _status(v)


@app.post("/v1/webhooks/test")
def webhook_test(request: Request):
    """Returns a signed sample event so customers can test their webhook verification code."""
    payload = json.dumps({"type": "verification.completed", "data": {"id": "ver_example", "status": "verified"}},
                         separators=(",", ":")).encode()
    return {"payload": payload.decode(), "signature": sign(payload, WEBHOOK_SECRET, int(time.time()))}
