"""Python SDK for the Integration Kit reference API.

Standard library only, so it drops into any customer codebase. Handles the parts integrations
usually get wrong: retries with Retry-After, idempotency keys, typed errors, webhook signatures.
"""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import uuid

__all__ = ["Client", "ApiError", "verify_webhook", "WebhookError"]
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, request_id: str | None):
        super().__init__(f"{status} {code}: {message} (request_id={request_id})")
        self.status, self.code, self.message, self.request_id = status, code, message, request_id


class WebhookError(Exception):
    pass


class Client:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000", *, max_retries: int = 3,
                 timeout: float = 10.0, sleep=time.sleep):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key, self.base_url = api_key, base_url.rstrip("/")
        self.max_retries, self.timeout, self._sleep = max_retries, timeout, sleep

    def _request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **(headers or {})}
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                if e.code in RETRY_STATUSES and attempt < self.max_retries:
                    retry_after = e.headers.get("Retry-After")
                    self._sleep(float(retry_after) if retry_after else min(2 ** attempt * 0.5, 8))
                    continue
                raise _api_error(e) from None
            except urllib.error.URLError:
                if attempt < self.max_retries:
                    self._sleep(min(2 ** attempt * 0.5, 8))
                    continue
                raise
        raise AssertionError("unreachable")

    def create_verification(self, user_ref: str, checks: list[str], *, idempotency_key: str | None = None) -> dict:
        # The same key is reused on every retry, so a timeout never creates two verifications.
        key = idempotency_key or str(uuid.uuid4())
        return self._request("POST", "/v1/verifications", {"user_ref": user_ref, "checks": checks},
                             {"Idempotency-Key": key})

    def get_verification(self, verification_id: str) -> dict:
        return self._request("GET", f"/v1/verifications/{verification_id}")

    def wait_for_result(self, verification_id: str, *, timeout: float = 30.0, interval: float = 0.5) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            v = self.get_verification(verification_id)
            if v["status"] != "pending" or time.monotonic() >= deadline:
                return v
            self._sleep(interval)


def _api_error(e: urllib.error.HTTPError) -> ApiError:
    rid = e.headers.get("X-Request-Id")
    try:
        err = json.loads(e.read()).get("error", {})
    except (ValueError, AttributeError):
        err = {}
    return ApiError(e.code, err.get("code", "http_error"), err.get("message", e.reason), err.get("request_id", rid))


def verify_webhook(payload: bytes, signature_header: str, secret: str, *, tolerance: int = 300, now=None) -> dict:
    """Verify an 'X-Signature: t=<unix>,v1=<hex>' header and return the parsed event."""
    try:
        parts = dict(p.split("=", 1) for p in signature_header.split(","))
        ts, sig = int(parts["t"]), parts["v1"]
    except (KeyError, ValueError):
        raise WebhookError("malformed signature header") from None
    if abs((now if now is not None else time.time()) - ts) > tolerance:
        raise WebhookError("timestamp outside tolerance (check the server clock or replayed event)")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise WebhookError("signature mismatch (wrong secret, or the body was changed before verifying)")
    return json.loads(payload)
