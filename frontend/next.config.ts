import type { NextConfig } from "next";

// Địa chỉ backend FastAPI. Trình duyệt chỉ gọi cùng domain `/api/*`; Next chuyển tiếp sang backend,
// nhờ đó cookie phiên là cookie cùng domain (không bị chặn như cookie bên thứ ba).
const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
