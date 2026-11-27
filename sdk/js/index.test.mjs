// Node 18+ built-in test runner. Uses a fake fetch so the SDK logic is tested without a server.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { Client, ApiError, verifyWebhook } from "./index.mjs";

const reply = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

test("retries 429 using Retry-After, then succeeds", async () => {
  const calls = [], waits = [];
  const fetchImpl = async (url, init) => {
    calls.push(init.headers["Idempotency-Key"]);
    return calls.length === 1 ? reply(429, { error: { code: "rate_limited" } }, { "Retry-After": "2" })
                              : reply(201, { id: "ver_1", status: "pending" });
  };
  const c = new Client("sk_test_demo", { fetchImpl, sleep: async (ms) => waits.push(ms) });
  const v = await c.createVerification("u", ["age_over_18"]);
  assert.equal(v.id, "ver_1");
  assert.deepEqual(waits, [2000]);
  assert.equal(calls[0], calls[1], "same idempotency key on retry");
});

test("surfaces structured errors with request id", async () => {
  const fetchImpl = async () => reply(401, { error: { code: "invalid_api_key", message: "no", request_id: "req_abc" } });
  const c = new Client("sk_bad", { fetchImpl });
  await assert.rejects(c.getVerification("ver_x"), (e) => e instanceof ApiError && e.requestId === "req_abc");
});

test("verifies webhook signatures and rejects tampering", async () => {
  const payload = '{"type":"verification.completed"}', ts = 1_800_000_000;
  const v1 = createHmac("sha256", "whsec_demo").update(`${ts}.${payload}`).digest("hex");
  const ok = await verifyWebhook(payload, `t=${ts},v1=${v1}`, "whsec_demo", { now: ts });
  assert.equal(ok.type, "verification.completed");
  await assert.rejects(verifyWebhook(payload + " ", `t=${ts},v1=${v1}`, "whsec_demo", { now: ts }), /mismatch/);
  await assert.rejects(verifyWebhook(payload, `t=${ts},v1=${v1}`, "whsec_demo", { now: ts + 3600 }), /tolerance/);
});
