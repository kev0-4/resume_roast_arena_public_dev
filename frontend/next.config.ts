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
};

export default nextConfig;
