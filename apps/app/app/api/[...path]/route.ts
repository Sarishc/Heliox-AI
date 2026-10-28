/**
 * Proxy /api/* to the backend. Streams responses (SSE included), forwards each
 * Set-Cookie (Next.js rewrites don't), and sets X-Forwarded-For only from a
 * trusted edge header. See lib/api-proxy.ts.
 */
import { createProxyHandler } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

const proxyRequest = createProxyHandler({
  target: process.env.API_PROXY_TARGET || "http://localhost:8000",
  clientIpHeader: process.env.TRUSTED_CLIENT_IP_HEADER || undefined,
});

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
