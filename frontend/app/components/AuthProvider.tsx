"use client";
/**
 * Thin client wrapper around NextAuth's SessionProvider.
 *
 * layout.tsx is a Server Component so it cannot use "use client" directly.
 * We put SessionProvider in this client-boundary file instead, and wrap the
 * whole app with it in layout.tsx.
 */
import { SessionProvider } from "next-auth/react";
import { ReactNode } from "react";

export default function AuthProvider({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
