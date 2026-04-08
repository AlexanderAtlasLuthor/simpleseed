/**
 * Next.js Edge Middleware — route protection.
 *
 * Runs on every request matched by the `config.matcher` below.
 * If the user has no valid NextAuth session cookie, they are redirected to /login.
 *
 * Public routes that never require auth:
 *   /login            — sign-in / sign-up page
 *   /api/auth/*       — NextAuth internal routes (session, CSRF, providers)
 *
 * All other routes require authentication.
 */
export { default } from "next-auth/middleware";

export const config = {
  matcher: [
    /*
     * Match every path EXCEPT:
     *   /_next/static    — Next.js static assets
     *   /_next/image     — image optimisation endpoint
     *   /favicon.ico     — browser favourite-icon request
     *   /login           — public sign-in page
     *   /api/auth/*      — NextAuth endpoints (must stay public)
     */
    "/((?!_next/static|_next/image|favicon.ico|login|api/auth).*)",
  ],
};
