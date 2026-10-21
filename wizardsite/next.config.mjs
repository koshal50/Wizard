/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.WIZARD_NEXT_DIST_DIR || ".next",
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  async rewrites() {
    const backend = process.env.WIZARD_ACCOUNT_BACKEND_URL || "http://127.0.0.1:8090"
    const url = new URL(backend)
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/" ||
        (url.protocol !== "https:" && !(process.env.WIZARD_ACCOUNT_LOCAL_DEV === "1" &&
          url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))) {
      throw new Error("Account backend must be an HTTPS origin (loopback HTTP is development-only)")
    }
    return {
      beforeFiles: ["/api/auth/:path*", "/api/cli/:path*", "/api/account/:path*", "/api/investigations/:path*",
        "/login", "/register", "/forgot-password", "/logout", "/oauth/oidc/:path*"]
        .map(source => ({ source, destination: backend.replace(/\/$/, "") + source })),
    }
  },
  async headers() {
    return [
      "/cli/:path*", "/login.html", "/register.html", "/forgot-password.html",
      "/api/auth/:path*", "/api/cli/:path*", "/api/account/:path*", "/api/investigations/:path*",
    ].map(source => ({ source, headers: [
      { key: "Cache-Control", value: "no-store" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Content-Type-Options", value: "nosniff" },
    ] }))
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
