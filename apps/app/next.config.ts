import type { NextConfig } from "next";

const apiTarget =
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8001";

const nextConfig: NextConfig = {
  async rewrites() {
    // /api is handled by app/api/[...path]/route.ts (forwards Set-Cookie; rewrites don't)
    return [
      { source: "/health", destination: `${apiTarget}/health` },
      { source: "/health/db", destination: `${apiTarget}/health/db` },
      { source: "/openapi.json", destination: `${apiTarget}/openapi.json` },
      { source: "/docs", destination: `${apiTarget}/docs` },
      { source: "/redoc", destination: `${apiTarget}/redoc` },
    ];
  },
};

export default nextConfig;
