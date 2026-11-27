# Customer integration guide

The plan I walk a customer team through, from first call to production. Each step has an exit check, so
both sides always know where the integration stands.

## 1. Discovery (day 1)
- Where in the customer's flow does verification happen (signup, checkout, age-gated content)?
- What happens to the user on `rejected`, and on a timeout?
- Which platforms: web, iOS, Android, backend? Who owns each?
- **Exit check:** one page with the flow, owners, and the success metric (for example "fewer than 1% of signups need manual review").

## 2. Sandbox in one hour
- Test key `sk_test_demo`, base URL of the sandbox, and `examples/quickstart.py` running on their machine.
- **Exit check:** they create a verification and see `verified`; `user_ref` starting with `fail` shows the `rejected` path.

## 3. Build the real flow
- Backend creates verifications with an `Idempotency-Key` derived from the business event.
- The browser or mobile app never holds the API key or the webhook secret; it talks to the customer's backend.
- Results arrive by webhook; polling (`wait_for_result`) only as a fallback.
- **Exit check:** `pytest`-style tests in their codebase for verified, rejected, timeout and 429.

## 4. Webhooks
- Verify the signature on the raw body (`verify_webhook` in both SDKs), reject events older than five minutes, make the handler idempotent by event id.
- **Exit check:** `POST /v1/webhooks/test` sample passes their handler; a tampered body fails.

## 5. Go live
- Production key in a secret manager, not in the repo or a mobile bundle.
- Log every `request_id`; alert on error rate, not on single errors.
- Rollout behind a feature flag to a small share of users first.
- **Exit check:** a week of production traffic with the success metric from step 1 met.

## 6. Hand-over
- Runbook link (`docs/TROUBLESHOOTING.md`), named contacts on both sides, and the open issues list.
