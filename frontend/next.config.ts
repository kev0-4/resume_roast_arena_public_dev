import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next's dev server blocks cross-origin requests to internal endpoints
  // (HMR's WebSocket included) by default -- fine for plain localhost
  // dev, but breaks when testing through a tunnel (a different host than
  // localhost). Read from an env var rather than hardcoding a specific
  // tunnel hostname, since a fresh `cloudflared tunnel` run gets a new
  // random hostname every time.
  allowedDevOrigins: process.env.NEXT_DEV_ALLOWED_ORIGIN
    ? [process.env.NEXT_DEV_ALLOWED_ORIGIN]
    : undefined,

  // Same-origin proxy to the backend, for testing on a real device.
  //
  // The mock interview needs getUserMedia, which browsers only grant on a
  // secure origin -- so a phone has to load the app over HTTPS. That then
  // makes a plain http://<lan-ip>:8000 backend unreachable as mixed
  // content. Proxying through the frontend's own origin means one URL,
  // one certificate, and no mixed content.
  //
  // The /_api prefix exists because the backend and the frontend genuinely
  // collide on real paths -- /leaderboard, /interview-leaderboard and
  // /r/[slug] are all both a page AND an API route -- so a blanket proxy
  // would shadow the pages. Set NEXT_PUBLIC_API_BASE_URL=/_api to use it.
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    const backend = process.env.BACKEND_PROXY_TARGET ?? "http://127.0.0.1:8000";
    return [{ source: "/_api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
