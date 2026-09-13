import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  typedRoutes: true,
  // Don't let `next dev` scaffold AGENTS.md/CLAUDE.md into this app; the repo
  // root owns agent guidance.
  agentRules: false,
  transpilePackages: [
    "@guitarista/tab-model",
    "@guitarista/music-theory",
    "@guitarista/api-types",
  ],
  // Convenience proxy: the browser normally calls FastAPI directly (CORS
  // allowlist), but `/api/*` on the Next origin also works.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
