# Integration troubleshooting playbook

How I support a customer integration: reproduce with their request id, match the symptom below, fix the
cause, and add the case to this page if it is new. Every API error carries `request_id`; ask for it first.

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 invalid_api_key` | Missing `Bearer ` prefix, test key in production, key with trailing newline from an env file | Log the first 8 characters of the key being sent; strip whitespace; check the environment |
| `422 unknown_check` | Typo or a check the plan does not include | The error lists the allowed checks; fix the request |
| `409 idempotency_conflict` | The same `Idempotency-Key` reused for a different request body | Derive the key from the business event (for example `signup-<user id>`), not from a constant |
| Two verifications for one signup | Client retried a timed-out POST without an idempotency key | Always send `Idempotency-Key`; both SDKs do this and reuse it on retry |
| `429 rate_limited` bursts | Batch job without backoff | Honour `Retry-After` (the SDKs do), or spread the batch |
| Verification stuck in `pending` | Polling too early or not at all | Use `wait_for_result` / webhooks; `pending` turns final after about a second in this reference API |
| Webhook `signature mismatch` | The body was parsed and re-serialised before verifying, or the wrong secret | Verify the raw request bytes exactly as received, then parse |
| Webhook `timestamp outside tolerance` | Server clock drift, or a replayed event | Sync the clock (NTP); treat old events as replays |
| Works on one pod, not another (Kubernetes) | This reference API keeps state in memory per pod | Run one replica for demos; production needs a shared store behind the API |

## Escalation note template

```
Customer:      <name>        Environment: <prod/staging>    Started: <UTC time>
Request ids:   req_...       SDK + version: <python 1.0.0 / js 1.0.0>
Expected:      <what should happen>
Actual:        <status code, error code, message>
Reproduced:    <yes/no, exact steps>
Impact:        <users blocked, workaround available?>
Next step:     <who owns it, by when>
```
