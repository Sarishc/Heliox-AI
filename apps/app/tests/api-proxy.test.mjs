// Tests for lib/api-proxy.ts against a real local HTTP "backend".
// Run: node --experimental-strip-types --test tests/   (Node >= 22.6)
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, test } from "node:test";
import { gzipSync } from "node:zlib";

import { createProxyHandler, trustedClientIp } from "../lib/api-proxy.ts";

const APP = "http://app.test";
let backend;
let target;
const seen = []; // requests the backend received
const closed = new Map(); // path -> ms when the backend saw the connection close

function route(req, res, body) {
  const url = new URL(req.url, "http://x");
  seen.push({ method: req.method, path: url.pathname + url.search, headers: req.headers, body });
  switch (url.pathname) {
    case "/api/v1/sse": {
      const opened = Date.now();
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      res.write("id: evt_1\nevent: budget.warning\ndata: {\"n\":1}\n\n");
      const timer = setInterval(() => res.write(": keepalive\n\n"), 200);
      res.on("close", () => {
        clearInterval(timer);
        closed.set(url.pathname + url.search, Date.now() - opened);
      });
      return;
    }
    case "/api/v1/no-content":
      res.writeHead(204, { "x-request-id": "req-204" });
      return res.end();
    case "/api/v1/not-modified":
      res.writeHead(304, { etag: '"abc"' });
      return res.end();
    case "/api/v1/cookies":
      res.setHeader("set-cookie", [
        "heliox_session=abc; Path=/; HttpOnly; SameSite=Strict",
        "heliox_csrf=xyz; Path=/; SameSite=Strict",
      ]);
      res.writeHead(200, { "content-type": "application/json" });
      return res.end('{"ok":true}');
    case "/api/v1/gzip": {
      const payload = gzipSync(Buffer.from('{"compressed":true}'));
      res.writeHead(200, { "content-type": "application/json", "content-encoding": "gzip", "content-length": payload.length });
      return res.end(payload);
    }
    case "/api/v1/download": {
      const bytes = Buffer.from([0, 1, 2, 250, 255, 10, 13]);
      res.writeHead(200, {
        "content-type": "application/octet-stream",
        "content-length": bytes.length,
        "content-disposition": 'attachment; filename="r.bin"',
      });
      return res.end(bytes);
    }
    case "/api/v1/echo":
      res.writeHead(200, { "content-type": "application/octet-stream" });
      return res.end(body);
    case "/api/v1/error":
      res.writeHead(422, { "content-type": "application/json", "x-request-id": "req-422" });
      return res.end('{"detail":"bad"}');
    case "/api/v1/teams":
      // FastAPI-style trailing-slash redirect back to the backend itself
      res.writeHead(307, { location: `${target}/api/v1/teams/` });
      return res.end();
    case "/api/v1/teams/":
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({ method: req.method, body: body.toString() }));
    case "/api/v1/auth/google":
      res.writeHead(302, { location: "https://accounts.example.com/o/oauth2/auth?x=1" });
      return res.end();
    case "/api/v1/headers":
      res.writeHead(200, { "content-type": "application/json", connection: "keep-alive, x-hop", "x-hop": "1" });
      return res.end("{}");
    default:
      res.writeHead(404, { "content-type": "application/json" });
      return res.end('{"detail":"Not Found"}');
  }
}

before(async () => {
  backend = createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => route(req, res, Buffer.concat(chunks)));
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  target = `http://127.0.0.1:${backend.address().port}`;
});

after(() => backend.close());

const proxy = (opts = {}) => createProxyHandler({ target, ...opts });
const lastSeen = () => seen[seen.length - 1];

test("SSE chunks arrive before the stream ends, with headers intact", async () => {
  const started = Date.now();
  const res = await proxy()(new Request(`${APP}/api/v1/sse?t=first`));
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("content-type"), "text/event-stream");
  assert.match(res.headers.get("cache-control"), /no-cache, no-transform/);
  assert.equal(res.headers.get("x-accel-buffering"), "no");
  assert.equal(res.headers.get("content-length"), null);
  const reader = res.body.getReader();
  const { value } = await reader.read();
  const text = new TextDecoder().decode(value);
  assert.match(text, /id: evt_1\nevent: budget.warning\ndata: \{"n":1\}/);
  assert.ok(Date.now() - started < 1000, "first event must not wait for the stream to finish");
  await reader.cancel();
});

test("cancelling the browser stream closes the upstream connection", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/sse?t=cancel`));
  const reader = res.body.getReader();
  await reader.read();
  await reader.cancel();
  await new Promise((r) => setTimeout(r, 300));
  assert.ok(closed.has("/api/v1/sse?t=cancel"), "upstream still open after cancel");
});

test("aborting the browser request aborts the upstream request", async () => {
  const controller = new AbortController();
  const res = await proxy()(new Request(`${APP}/api/v1/sse?t=abort`, { signal: controller.signal }));
  await res.body.getReader().read();
  controller.abort();
  await new Promise((r) => setTimeout(r, 300));
  assert.ok(closed.has("/api/v1/sse?t=abort"), "upstream still open after abort");
});

test("204 and 304 have no body and keep their status", async () => {
  const noContent = await proxy()(new Request(`${APP}/api/v1/no-content`, { method: "DELETE" }));
  assert.equal(noContent.status, 204);
  assert.equal(noContent.body, null);
  assert.equal(noContent.headers.get("x-request-id"), "req-204");
  const notModified = await proxy()(new Request(`${APP}/api/v1/not-modified`));
  assert.equal(notModified.status, 304);
  assert.equal(notModified.headers.get("etag"), '"abc"');
});

test("each Set-Cookie header is forwarded separately", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/cookies`, { method: "POST", body: "x" }));
  assert.deepEqual(res.headers.getSetCookie(), [
    "heliox_session=abc; Path=/; HttpOnly; SameSite=Strict",
    "heliox_csrf=xyz; Path=/; SameSite=Strict",
  ]);
});

test("cookies from the browser reach the backend", async () => {
  await proxy()(new Request(`${APP}/api/v1/cookies`, { headers: { cookie: "heliox_session=abc" } }));
  assert.equal(lastSeen().headers.cookie, "heliox_session=abc");
});

test("decoded gzip responses drop content-encoding and content-length", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/gzip`));
  assert.equal(res.headers.get("content-encoding"), null);
  assert.equal(res.headers.get("content-length"), null);
  assert.deepEqual(await res.json(), { compressed: true });
});

test("binary downloads keep bytes, length and disposition", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/download`));
  assert.equal(res.headers.get("content-length"), "7");
  assert.equal(res.headers.get("content-disposition"), 'attachment; filename="r.bin"');
  assert.deepEqual([...new Uint8Array(await res.arrayBuffer())], [0, 1, 2, 250, 255, 10, 13]);
});

test("binary request bodies are forwarded byte for byte", async () => {
  const bytes = new Uint8Array([0, 255, 128, 10, 13, 0]);
  const res = await proxy()(new Request(`${APP}/api/v1/echo`, { method: "PUT", body: bytes }));
  assert.deepEqual([...new Uint8Array(await res.arrayBuffer())], [...bytes]);
  assert.equal(lastSeen().headers["content-length"], "6");
});

test("error statuses and JSON bodies pass through", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/error`));
  assert.equal(res.status, 422);
  assert.equal(res.headers.get("x-request-id"), "req-422");
  assert.deepEqual(await res.json(), { detail: "bad" });
  assert.equal((await proxy()(new Request(`${APP}/api/v1/missing`))).status, 404);
});

test("redirects back to the backend are followed with method and body", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/teams`, { method: "POST", body: '{"a":1}' }));
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { method: "POST", body: '{"a":1}' });
});

test("redirects elsewhere go to the browser untouched", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/auth/google`));
  assert.equal(res.status, 302);
  assert.equal(res.headers.get("location"), "https://accounts.example.com/o/oauth2/auth?x=1");
});

test("hop-by-hop headers are not forwarded in either direction", async () => {
  const res = await proxy()(new Request(`${APP}/api/v1/headers`, { headers: { "x-custom": "kept" } }));
  assert.equal(res.headers.get("x-hop"), null);
  assert.equal(res.headers.get("connection"), null);
  assert.equal(lastSeen().headers["x-custom"], "kept");
});

test("client-supplied forwarding headers never reach the backend", async () => {
  await proxy()(
    new Request(`${APP}/api/v1/headers`, {
      headers: {
        "x-forwarded-for": "203.0.113.9",
        forwarded: "for=203.0.113.9",
        "x-real-ip": "203.0.113.9",
        "x-forwarded-host": "evil.example",
        "cf-connecting-ip": "203.0.113.9",
      },
    })
  );
  const h = lastSeen().headers;
  for (const name of ["x-forwarded-for", "forwarded", "x-real-ip", "x-forwarded-host", "cf-connecting-ip"]) {
    assert.equal(h[name], undefined, `${name} leaked`);
  }
});

test("X-Forwarded-For is set only from the configured trusted edge header", async () => {
  const handler = proxy({ clientIpHeader: "x-real-ip" });
  await handler(new Request(`${APP}/api/v1/headers`, { headers: { "x-real-ip": "198.51.100.7", "x-forwarded-for": "1.1.1.1" } }));
  assert.equal(lastSeen().headers["x-forwarded-for"], "198.51.100.7");
  await handler(new Request(`${APP}/api/v1/headers`, { headers: { "x-real-ip": "not-an-ip" } }));
  assert.equal(lastSeen().headers["x-forwarded-for"], undefined);
});

test("trustedClientIp takes the edge's own (last) entry and validates it", () => {
  const req = (v) => new Request(APP, { headers: { "x-forwarded-for": v } });
  assert.equal(trustedClientIp(req("1.2.3.4, 198.51.100.7"), "x-forwarded-for"), "198.51.100.7");
  assert.equal(trustedClientIp(req("2001:db8::1"), "x-forwarded-for"), "2001:db8::1");
  assert.equal(trustedClientIp(req("::ffff:198.51.100.7"), "x-forwarded-for"), "198.51.100.7");
  assert.equal(trustedClientIp(req("198.51.100.7:443"), "x-forwarded-for"), null);
  assert.equal(trustedClientIp(req("198.51.100.7"), undefined), null);
});

test("an unreachable backend is a 502 JSON error, not a crash", async () => {
  const res = await createProxyHandler({ target: "http://127.0.0.1:9" })(new Request(`${APP}/api/v1/teams`));
  assert.equal(res.status, 502);
  assert.equal((await res.json()).error, "bad_gateway");
});
