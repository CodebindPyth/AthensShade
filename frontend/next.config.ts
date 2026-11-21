import type { NextConfig } from "next"

const backendUrl = (process.env.ATHENSSHADE_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "")

const config: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }]
  },
}

export default config
