# integration-kit

A reference identity-verification API with Python and JavaScript SDKs, deployment to Docker and Kubernetes,
and the playbooks I use to take a customer from first call to production.

I built it to show the forward-deployed part of engineering work: the code that makes an integration
reliable on the customer's side (retries, idempotency, webhook signatures, actionable errors), and the
written guidance that gets their team there.

## What is inside

| Part | What it shows |
|---|---|
| `server/app.py` | FastAPI reference API: API-key auth, idempotent creates, rate limiting with `Retry-After`, structured errors with request ids, signed webhooks, health and readiness probes |
| `sdk/python/` | Standard-library Python SDK: retries with backoff, idempotency key reused on retry, typed `ApiError`, `verify_webhook` |
| `sdk/js/` | Dependency-free JavaScript SDK for browser, Node 18+ and React Native, same contract as the Python SDK |
| `k8s/` | Hardened Kubernetes manifests (non-root, read-only filesystem, probes, resource limits) and a kind end-to-end script |
| `docs/INTEGRATION_GUIDE.md` | Step-by-step customer plan with an exit check per step |
| `docs/TROUBLESHOOTING.md` | Symptom, cause and fix table, plus an escalation template |
| `examples/quickstart.py` | Five-minute integration a customer can run |

## Run it

```bash
uv sync
make test          # 6 Python end-to-end tests (SDK against the real server) + 3 JavaScript tests
make run           # API on http://localhost:8000, docs on /docs
python3 examples/quickstart.py
make e2e           # kind cluster, image build, Kubernetes deploy, SDK smoke test through the Service
```

CI runs the tests and the kind deployment on every push.

## Design notes

- **Idempotency first.** A timed-out POST is the most common source of duplicate records in integrations, so
  both SDKs generate an idempotency key once and reuse it on every retry; the server returns the original
  object, or `409` if the key is reused with a different body.
- **Errors a customer can act on.** Every error has a stable `code`, a message that says what to change, and a
  `request_id` that support can trace.
- **Secrets stay on the server.** The JavaScript SDK runs in browsers, but webhook verification and API keys
  belong on the customer's backend; the docs say so where it matters.
- **Honest limits.** State is in memory, so the Kubernetes demo runs one replica; production would put a shared
  store behind the API. Verification outcomes are deterministic (`user_ref` starting with `fail` is rejected)
  so integrations can be tested.

## License

MIT
