/**
 * Streaming reverse proxy from the Next.js server to the FastAPI backend (/api/*).
 *
 * - Response bodies are streamed as they arrive (SSE works, nothing is buffered),
 *   and cancelling the browser request aborts the upstream request.
 * - Set-Cookie headers are forwarded individually (Next.js rewrites drop them).
 * - Redirects back to the backend (FastAPI's trailing-slash 307s) are followed
 *   here; any other redirect (e.g. an OAuth provider) goes to the browser as is.
 * - Client-supplied forwarding headers (X-Forwarded-For, Forwarded, X-Real-IP…)
 *   are stripped. The backend trusts X-Forwarded-For only from this proxy, so we
 *   set it only from TRUSTED_CLIENT_IP_HEADER: a header written by the edge in
 *   front of Next.js (e.g. "x-real-ip" on Vercel). Without it, no client address
 *   is forwarded and the backend treats this proxy as a shared client.
 *
 * No Next.js imports, so it runs under plain Node for tests.
 */
import { isIP } from "node:net";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-connection",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const FORWARDING = new Set([
  "forwarded",
  "x-forwarded-for",
  "x-forwarded-host",
  "x-forwarded-port",
  "x-forwarded-prefix",
  "x-forwarded-proto",
  "x-real-ip",
  "x-client-ip",
  "x-cluster-client-ip",
  "true-client-ip",
  "cf-connecting-ip",
  "fastly-client-ip",
  "x-original-forwarded-for",
  "x-vercel-forwarded-for",
]);

// fetch decodes these itself, so the encoding/length headers no longer describe the body
const DECODED_ENCODINGS = new Set(["gzip", "x-gzip", "deflate", "br"]);
const NULL_BODY_STATUS = new Set([204, 205, 304]);
const MAX_REDIRECTS = 5;

export interface ProxyOptions {
  target: string;
  clientIpHeader?: string;
  fetchImpl?: typeof fetch;
}

/** Client IP from the trusted edge's header: its last entry, which the edge itself wrote. */
export function trustedClientIp(request: Request, header?: string): string | null {
  if (!header) return null;
  const raw = request.headers.get(header);
  if (!raw) return null;
  const parts = raw.split(",").map((part) => part.trim());
  let ip = parts[parts.length - 1] ?? "";
  if (ip.toLowerCase().startsWith("::ffff:") && isIP(ip.slice(7)) === 4) ip = ip.slice(7);
  return isIP(ip) ? ip : null;
}

function connectionTokens(headers: Headers): Set<string> {
  return new Set(
    (headers.get("connection") ?? "")
      .split(",")
      .map((token) => token.trim().toLowerCase())
      .filter(Boolean)
  );
}

function upstreamHeaders(request: Request, clientIp: string | null): Headers {
  const named = connectionTokens(request.headers);
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const name = key.toLowerCase();
    if (
      name === "host" ||
      name === "content-length" ||
      name === "accept-encoding" ||
      HOP_BY_HOP.has(name) ||
      named.has(name) ||
      FORWARDING.has(name) ||
      name.startsWith("x-forwarded-")
    ) {
      return;
    }
    headers.set(key, value);
  });
  if (clientIp) headers.set("x-forwarded-for", clientIp);
  return headers;
}

function downstreamHeaders(res: Response): Headers {
  const named = connectionTokens(res.headers);
  const encoding = (res.headers.get("content-encoding") ?? "").trim().toLowerCase();
  const decoded = DECODED_ENCODINGS.has(encoding);
  const headers = new Headers();
  res.headers.forEach((value, key) => {
    const name = key.toLowerCase();
    if (name === "set-cookie" || HOP_BY_HOP.has(name) || named.has(name)) return;
    if (decoded && (name === "content-encoding" || name === "content-length")) return;
    headers.set(key, value);
  });
  // forEach folds Set-Cookie into one value; each cookie must stay its own header
  for (const cookie of res.headers.getSetCookie()) headers.append("set-cookie", cookie);

  if ((res.headers.get("content-type") ?? "").toLowerCase().startsWith("text/event-stream")) {
    // no-transform keeps compression and intermediaries from buffering the stream
    const cacheControl = res.headers.get("cache-control");
    if (!cacheControl || !/no-transform/i.test(cacheControl)) {
      headers.set("cache-control", cacheControl ? `${cacheControl}, no-transform` : "no-cache, no-transform");
    }
    headers.set("x-accel-buffering", "no");
  }
  return headers;
}

export function createProxyHandler({ target, clientIpHeader, fetchImpl = fetch }: ProxyOptions) {
  const targetOrigin = new URL(target).origin;

  return async function proxyRequest(request: Request): Promise<Response> {
    const incoming = new URL(request.url);
    let url = new URL(`${incoming.pathname}${incoming.search}`, target);
    let method = request.method.toUpperCase();
    const headers = upstreamHeaders(request, trustedClientIp(request, clientIpHeader));
    // Raw bytes, so binary uploads survive; request bodies are bounded, unlike responses
    let body: ArrayBuffer | undefined =
      method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

    try {
      for (let hop = 0; ; hop++) {
        const res = await fetchImpl(url, {
          method,
          headers,
          body,
          redirect: "manual",
          signal: request.signal,
          cache: "no-store",
        });

        const location = res.headers.get("location");
        if (res.status >= 300 && res.status < 400 && location && hop < MAX_REDIRECTS) {
          const next = new URL(location, url);
          if (next.origin === targetOrigin) {
            await res.body?.cancel();
            if (res.status === 303 || ((res.status === 301 || res.status === 302) && method === "POST")) {
              method = "GET";
              body = undefined;
            }
            url = next;
            continue;
          }
        }

        const responseHeaders = downstreamHeaders(res);
        if (method === "HEAD" || NULL_BODY_STATUS.has(res.status)) {
          await res.body?.cancel();
          return new Response(null, { status: res.status, statusText: res.statusText, headers: responseHeaders });
        }
        return new Response(res.body, { status: res.status, statusText: res.statusText, headers: responseHeaders });
      }
    } catch (error) {
      if (request.signal.aborted) {
        // The browser went away; there is nobody to answer
        return new Response(null, { status: 499 });
      }
      console.error("API proxy: upstream request failed", (error as Error)?.message);
      return Response.json(
        { error: "bad_gateway", message: "The API is temporarily unreachable." },
        { status: 502 }
      );
    }
  };
}
