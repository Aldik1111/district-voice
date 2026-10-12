import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const nextConfig: NextConfig = {
  // Local CPU inference is synchronous; allow the bounded analysis run to finish.
  experimental: { proxyTimeout: 600_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
