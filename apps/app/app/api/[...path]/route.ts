/**
 * Proxy API requests to backend, forwarding all headers including Set-Cookie.
 * Next.js rewrites don't forward Set-Cookie, so we use a route handler for cookie auth.
 */
import { NextRequest, NextResponse } from "next/server";

const API_TARGET = process.env.API_PROXY_TARGET || "http://localhost:8001";

async function proxyRequest(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const pathStr = path.join("/");
  const url = new URL(request.url);
  const backendUrl = `${API_TARGET}/api/${pathStr}${url.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (
      !["host", "connection", "content-length"].includes(key.toLowerCase())
    ) {
      headers.set(key, value);
    }
  });

  const init: RequestInit = {
    method: request.method,
    headers,
  };
  if (["POST", "PUT", "PATCH"].includes(request.method)) {
    init.body = await request.text();
  }

  const res = await fetch(backendUrl, init);
  const body = await res.arrayBuffer();

  const responseHeaders = new Headers();
  res.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "set-cookie") {
      responseHeaders.set(key, value);
    }
  });
  // Fetch API forbids reading Set-Cookie via forEach; use getSetCookie() for proxy
  const setCookies = (res.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie?.();
  if (setCookies?.length) {
    setCookies.forEach((cookie) => {
      responseHeaders.append("Set-Cookie", cookie);
    });
  }

  return new NextResponse(body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
