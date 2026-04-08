/**
 * NextAuth v4 Route Handler for Next.js App Router.
 *
 * This file is at app/api/auth/[...nextauth]/route.ts and handles all
 * /api/auth/* requests INSIDE Next.js — it is NOT proxied to FastAPI.
 *
 * Flow:
 *   1. User submits /login form → signIn("credentials", { email, password })
 *   2. NextAuth calls authorize() here
 *   3. authorize() calls POST /api/auth/login on the FastAPI backend directly
 *   4. FastAPI returns { access_token, user: { id, email } }
 *   5. NextAuth stores access_token in its encrypted JWT session cookie
 *   6. Frontend reads session.accessToken and sends it as Bearer token
 */
import NextAuth, { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

// Server-side backend URL (not exposed in browser bundle).
// Falls back to the rewrite target so local dev works without extra config.
const BACKEND_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const authOptions: NextAuthOptions = {
  // Use JWT-based sessions (stateless, no DB required on the Next.js side).
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 24, // 24 hours — mirrors the FastAPI token lifetime
  },

  pages: {
    signIn: "/login", // redirect here when auth is required
  },

  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },

      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        try {
          // Call FastAPI directly (server-side, not via Next.js rewrite).
          const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });

          if (!res.ok) return null; // wrong credentials → NextAuth shows error

          const data = await res.json();
          // Return object shape that NextAuth will store in the JWT token.
          return {
            id: data.user.id,
            email: data.user.email,
            accessToken: data.access_token,
          };
        } catch {
          // Network error or backend down — return null so NextAuth shows error.
          return null;
        }
      },
    }),
  ],

  callbacks: {
    /**
     * Called when the JWT is created (sign-in) or updated (page refresh).
     * We store the FastAPI access_token in the JWT so we can forward it to
     * the backend on every authenticated API call.
     */
    async jwt({ token, user }) {
      if (user) {
        // First call after sign-in — persist the backend token.
        token.accessToken = (user as { accessToken: string }).accessToken;
        token.userId = user.id;
        token.email = user.email ?? token.email;
      }
      return token;
    },

    /**
     * Called when the client accesses the session.
     * Expose accessToken so client components can attach it to API requests.
     */
    async session({ session, token }) {
      (session as unknown as { accessToken: string }).accessToken =
        token.accessToken as string;
      if (session.user) {
        session.user.id = token.userId as string;
      }
      return session;
    },
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
