// JavaScript SDK for the Integration Kit reference API (browser, Node 18+, React Native).
// No dependencies: fetch + Web Crypto. Mirrors the Python SDK so web and server teams integrate the same way.

const RETRY = new Set([429, 500, 502, 503, 504]);

export class ApiError extends Error {
  constructor(status, code, message, requestId) {
    super(`${status} ${code}: ${message} (request_id=${requestId})`);
    Object.assign(this, { status, code, requestId });
  }
}

export class Client {
  constructor(apiKey, { baseUrl = "http://localhost:8000", maxRetries = 3, fetchImpl = fetch, sleep } = {}) {
    if (!apiKey) throw new Error("apiKey is required");
    Object.assign(this, { apiKey, baseUrl: baseUrl.replace(/\/$/, ""), maxRetries, fetchImpl });
    this.sleep = sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
  }

  async #request(method, path, body, headers = {}) {
    for (let attempt = 0; ; attempt++) {
      const res = await this.fetchImpl(this.baseUrl + path, {
        method,
        headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json", ...headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (res.ok) return res.json();
      if (RETRY.has(res.status) && attempt < this.maxRetries) {
        const ra = res.headers.get("Retry-After");
        await this.sleep(ra ? Number(ra) * 1000 : Math.min(500 * 2 ** attempt, 8000));
        continue;
      }
      const err = (await res.json().catch(() => ({}))).error ?? {};
      throw new ApiError(res.status, err.code ?? "http_error", err.message ?? res.statusText,
        err.request_id ?? res.headers.get("X-Request-Id"));
    }
  }

  createVerification(userRef, checks, { idempotencyKey = crypto.randomUUID() } = {}) {
    return this.#request("POST", "/v1/verifications", { user_ref: userRef, checks }, { "Idempotency-Key": idempotencyKey });
  }

  getVerification(id) {
    return this.#request("GET", `/v1/verifications/${encodeURIComponent(id)}`);
  }
}

// Verify 'X-Signature: t=<unix>,v1=<hex>' on the server side. Never ship the webhook secret to a browser.
export async function verifyWebhook(payload, header, secret, { tolerance = 300, now = Date.now() / 1000 } = {}) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=", 2)));
  const ts = Number(parts.t);
  if (!ts || !parts.v1) throw new Error("malformed signature header");
  if (Math.abs(now - ts) > tolerance) throw new Error("timestamp outside tolerance");
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(`${ts}.${payload}`)));
  const hex = [...mac].map((b) => b.toString(16).padStart(2, "0")).join("");
  if (hex.length !== parts.v1.length || [...hex].reduce((d, c, i) => d | (c.charCodeAt(0) ^ parts.v1.charCodeAt(i)), 0))
    throw new Error("signature mismatch");
  return JSON.parse(payload);
}
