// Auth0 sign-in through lib/api-proxy.ts, against a real local HTTP "backend".
// Run: node --experimental-strip-types --test tests/   (Node >= 22.6)
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, test } from "node:test";

import { createProxyHandler } from "../lib/api-proxy.ts";

const APP = "http://app.test";
const AUTHORIZE = "https://tenant.example.auth0.com/authorize?state=s&nonce=n";
const BINDING = "heliox_auth0_tx=binding; HttpOnly; Max-Age=600; Path=/api/v1/auth/auth0; SameSite=lax";
const BINDING_CLEARED = 'heliox_auth0_tx=""; HttpOnly; Max-Age=0; Path=/api/v1/auth/auth0; SameSite=lax';
const SESSION = "heliox_session=signed.jwt.value; HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure";

let backend;
let target;
let hops = 0;
let lastHeaders = {};
let streamClosed = false;

before(async () => {
  backend = createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    lastHeaders = req.headers;
    hops += 1;
    switch (url.pathname) {
      case "/api/v1/auth/auth0/login":
        res.setHeader("set-cookie", [BINDING]);
        res.writeHead(302, { location: AUTHORIZE });
        return res.end();
      case "/api/v1/auth/auth0/callback":
        if (url.searchParams.get("state") === "good") {
          res.setHeader("set-cookie", [BINDING_CLEARED, SESSION]);
          res.writeHead(302, { location: `${APP}/onboarding` });
        } else {
          res.setHeader("set-cookie", [BINDING_CLEARED]);
          res.writeHead(302, { location: `${APP}/login?error=auth0_state` });
        }
        return res.end();
      case "/api/v1/auth/auth0/callback/":
        // FastAPI's trailing-slash redirect back to the backend itself
        res.writeHead(307, { location: `${target}/api/v1/auth/auth0/callback${url.search}` });
        return res.end();
      case "/api/v1/redirect-loop":
        res.writeHead(307, { location: `${target}/api/v1/redirect-loop` });
        return res.end();
      case "/api/v1/stream":
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
        res.write(": connected\n\n");
        res.on("close", () => (streamClosed = true));
        return;
      case "/api/v1/binary":
        res.writeHead(200, { "content-type": "application/octet-stream" });
        return res.end(Buffer.from([0, 1, 2, 250, 255, 10, 13]));
      case "/api/v1/json":
        res.writeHead(200, { "content-type": "application/json" });
        return res.end('{"ok":true}');
      case "/api/v1/denied":
        res.writeHead(401, { "content-type": "application/json" });
        return res.end('{"message":"Not authenticated"}');
      default:
        res.writeHead(404);
        return res.end();
    }
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  target = `http://127.0.0.1:${backend.address().port}`;
});

after(() => {
  backend.closeAllConnections();
  backend.close();
});

function proxy(path, init, options = {}) {
  return createProxyHandler({ target, ...options })(new Request(`${APP}${path}`, init));
}

test("Auth0 login: the 302 and the browser-binding cookie reach the browser", async () => {
  const res = await proxy("/api/v1/auth/auth0/login");

  assert.equal(res.status, 302);
  assert.equal(res.headers.get("location"), AUTHORIZE);
  assert.deepEqual(res.headers.getSetCookie(), [BINDING]);
});

test("Auth0 callback: the 302, session cookie and binding deletion all survive, separately", async () => {
  const res = await proxy("/api/v1/auth/auth0/callback?code=c&state=good");

  assert.equal(res.status, 302);
  assert.equal(res.headers.get("location"), `${APP}/onboarding`);
  assert.deepEqual(res.headers.getSetCookie(), [BINDING_CLEARED, SESSION]);
});

test("session cookie attributes are unchanged and the token isn't exposed elsewhere", async () => {
  const res = await proxy("/api/v1/auth/auth0/callback?code=c&state=good");

  const session = res.headers.getSetCookie().find((cookie) => cookie.startsWith("heliox_session="));
  assert.equal(session, SESSION);
  assert.ok(!session.toLowerCase().includes("domain="));
  assert.ok(!res.headers.get("location").includes("signed.jwt.value"));
  assert.ok(!(await res.text()).includes("signed.jwt.value"));
});

test("invalid state: back to login, binding cleared, no session", async () => {
  const res = await proxy("/api/v1/auth/auth0/callback?code=c&state=bad");

  assert.equal(res.status, 302);
  assert.equal(res.headers.get("location"), `${APP}/login?error=auth0_state`);
  assert.deepEqual(res.headers.getSetCookie(), [BINDING_CLEARED]);
});

test("a trailing-slash callback is followed inside the proxy and keeps its cookies", async () => {
  const res = await proxy("/api/v1/auth/auth0/callback/?code=c&state=good");

  assert.equal(res.status, 302);
  assert.equal(res.headers.get("location"), `${APP}/onboarding`);
  assert.deepEqual(res.headers.getSetCookie(), [BINDING_CLEARED, SESSION]);
});

test("the request can't choose the redirect destination", async () => {
  const res = await proxy("/api/v1/auth/auth0/callback?state=bad&redirect=https://evil.example&location=https://evil.example");

  assert.equal(res.headers.get("location"), `${APP}/login?error=auth0_state`);
});

test("internal redirects are bounded", async () => {
  hops = 0;
  const res = await proxy("/api/v1/redirect-loop");

  assert.equal(res.status, 307);
  assert.equal(hops, 6); // the first request and five followed redirects
});

test("SSE still streams before the response ends, and cancelling closes upstream", async () => {
  streamClosed = false;
  const res = await proxy("/api/v1/stream");

  assert.equal(res.status, 200);
  assert.ok(res.headers.get("content-type").startsWith("text/event-stream"));
  assert.match(res.headers.get("cache-control"), /no-transform/);
  assert.equal(res.headers.get("x-accel-buffering"), "no");
  const reader = res.body.getReader();
  const { value } = await reader.read();
  assert.equal(new TextDecoder().decode(value), ": connected\n\n");

  await reader.cancel();
  for (let i = 0; i < 50 && !streamClosed; i++) await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(streamClosed);
});

test("forwarded client identity can't be spoofed on the Auth0 routes", async () => {
  const spoofed = {
    headers: {
      "x-forwarded-for": "6.6.6.6",
      forwarded: "for=6.6.6.6",
      "x-real-ip": "6.6.6.6",
      "x-forwarded-host": "evil.example",
      "x-forwarded-proto": "https",
      "true-client-ip": "6.6.6.6",
    },
  };

  await proxy("/api/v1/auth/auth0/login", spoofed);
  for (const name of Object.keys(spoofed.headers)) assert.equal(lastHeaders[name], undefined, name);

  await proxy("/api/v1/auth/auth0/login", { headers: { ...spoofed.headers, "x-edge-ip": "203.0.113.9" } }, {
    clientIpHeader: "x-edge-ip",
  });
  assert.equal(lastHeaders["x-forwarded-for"], "203.0.113.9");
});

test("the binding cookie from the browser reaches the backend", async () => {
  await proxy("/api/v1/auth/auth0/callback?state=good", { headers: { cookie: "heliox_auth0_tx=binding" } });

  assert.equal(lastHeaders.cookie, "heliox_auth0_tx=binding");
});

test("binary and ordinary API responses are unchanged", async () => {
  const binary = await proxy("/api/v1/binary");
  assert.deepEqual([...new Uint8Array(await binary.arrayBuffer())], [0, 1, 2, 250, 255, 10, 13]);

  const json = await proxy("/api/v1/json");
  assert.deepEqual(await json.json(), { ok: true });

  const denied = await proxy("/api/v1/denied");
  assert.equal(denied.status, 401);
  assert.deepEqual(await denied.json(), { message: "Not authenticated" });
});

test("an injected fetch sees manual redirects, so nothing is followed out to Auth0", async () => {
  const seen = [];
  const fetchImpl = async (url, init) => {
    seen.push(init.redirect);
    return new Response(null, { status: 302, headers: { location: AUTHORIZE } });
  };

  const res = await proxy("/api/v1/auth/auth0/login", undefined, { fetchImpl });

  assert.deepEqual(seen, ["manual"]);
  assert.equal(res.headers.get("location"), AUTHORIZE);
});
