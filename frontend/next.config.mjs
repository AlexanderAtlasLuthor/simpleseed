/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        // Proxy /api/* to the FastAPI backend.
        // IMPORTANT: Next.js Route Handlers (files under app/api/) take priority
        // over rewrites, so /api/auth/[...nextauth] is handled by Next.js and
        // is NOT forwarded to FastAPI.  The FastAPI backend exposes its own
        // /api/auth/login and /api/auth/register — those are called server-side
        // from NextAuth's authorize() function, not via this rewrite.
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;