"""End-to-end tests: the Python SDK against the real FastAPI app on a local port."""

import socket
import threading
import time

import pytest
import uvicorn

from integration_kit import ApiError, Client, WebhookError, verify_webhook
from server import app as server


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True


def test_create_and_wait_for_verified(base_url):
    c = Client("sk_test_demo", base_url)
    v = c.create_verification("user_42", ["age_over_18"])
    assert v["status"] == "pending" and v["id"].startswith("ver_")
    assert c.wait_for_result(v["id"], timeout=5)["status"] == "verified"


def test_rejected_outcome_is_deterministic(base_url):
    c = Client("sk_test_demo", base_url)
    v = c.create_verification("fail_user", ["document"])
    assert c.wait_for_result(v["id"], timeout=5)["status"] == "rejected"


def test_idempotency_returns_same_object_and_detects_conflicts(base_url):
    c = Client("sk_test_demo", base_url)
    a = c.create_verification("user_1", ["liveness"], idempotency_key="order-1")
    b = c.create_verification("user_1", ["liveness"], idempotency_key="order-1")
    assert a["id"] == b["id"]
    with pytest.raises(ApiError) as e:
        c.create_verification("user_2", ["liveness"], idempotency_key="order-1")
    assert e.value.status == 409 and e.value.code == "idempotency_conflict"


def test_bad_key_and_unknown_check_give_actionable_errors(base_url):
    with pytest.raises(ApiError) as e:
        Client("sk_wrong", base_url).get_verification("ver_x")
    assert e.value.status == 401 and e.value.request_id.startswith("req_")
    with pytest.raises(ApiError) as e:
        Client("sk_test_demo", base_url).create_verification("u", ["blood_type"])
    assert e.value.code == "unknown_check" and "age_over_18" in e.value.message


def test_rate_limit_is_retried_with_retry_after(base_url, monkeypatch):
    monkeypatch.setattr(server, "RATE_PER_MINUTE", 2)
    server._buckets.clear()
    waits = []
    c = Client("sk_test_demo", base_url, max_retries=1, sleep=waits.append)
    c.get_verification(c.create_verification("u", ["document"])["id"])
    with pytest.raises(ApiError) as e:  # third call in the window: retried once, then surfaced
        c.get_verification("ver_missing")
    assert e.value.status == 429 and waits and waits[0] >= 1
    server._buckets.clear()


def test_webhook_signature_round_trip(base_url):
    sample = Client("sk_test_demo", base_url)._request("POST", "/v1/webhooks/test")
    event = verify_webhook(sample["payload"].encode(), sample["signature"], "whsec_demo")
    assert event["type"] == "verification.completed"
    with pytest.raises(WebhookError, match="mismatch"):
        verify_webhook(sample["payload"].encode() + b" ", sample["signature"], "whsec_demo")
    with pytest.raises(WebhookError, match="tolerance"):
        verify_webhook(sample["payload"].encode(), sample["signature"], "whsec_demo", now=time.time() + 3600)
