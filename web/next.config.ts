import type { NextConfig } from "next";

// In local dev the Python backend (FastAPI) runs on a separate port.
// Proxy the Python-owned routes to it; /api/ai stays a Next.js route.
const PYTHON_API_BASE = process.env.PYTHON_API_BASE ?? "http://127.0.0.1:3001";

const config: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/chat", destination: `${PYTHON_API_BASE}/api/chat` },
      { source: "/api/agent", destination: `${PYTHON_API_BASE}/api/agent` },
      { source: "/api/cron/:path*", destination: `${PYTHON_API_BASE}/api/cron/:path*` },
    ];
  },
};

export default config;
