"""Five-minute integration: create a verification, wait for the result, verify a webhook.

Run against a local server (make run) or any deployment: IK_BASE_URL=... python3 examples/quickstart.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))
from integration_kit import ApiError, Client, verify_webhook  # noqa: E402

client = Client(os.environ.get("IK_API_KEY", "sk_test_demo"), os.environ.get("IK_BASE_URL", "http://localhost:8000"))
try:
    v = client.create_verification("customer_123", ["age_over_18"], idempotency_key="signup-customer_123")
    print("created:", v["id"], v["status"])
    print("result: ", client.wait_for_result(v["id"], timeout=10)["status"])
    sample = client._request("POST", "/v1/webhooks/test")
    event = verify_webhook(sample["payload"].encode(), sample["signature"], os.environ.get("IK_WEBHOOK_SECRET", "whsec_demo"))
    print("webhook:", event["type"], "signature ok")
except ApiError as e:
    # Always log the request id: it is the first thing support asks for.
    sys.exit(f"API error {e.status} {e.code}: {e.message} (request_id={e.request_id})")
