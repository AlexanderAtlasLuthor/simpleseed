/**
 * Authenticated API client.
 *
 * Usage — replace every bare `fetch("/api/...")` call with `apiFetch("/api/...")`.
 * The helper reads the NextAuth session and attaches the FastAPI Bearer token.
 *
 * Example:
 *   const res = await apiFetch("/api/rfps");
 *   const res = await apiFetch("/api/analyze", { method: "POST", body: formData });
 *
 * getSession() works in both browser and server contexts, so apiFetch can be
 * used in Client Components (useEffect, event handlers) and Server Components.
 *
 * 401/403 handling: if the backend returns 401 or 403 (expired/invalid token),
 * the session is signed out automatically and the user is sent to /login,
 * preventing silent failures when the JWT has expired.
 */
import { getSession, signOut } from "next-auth/react";

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const session = await getSession();
  const accessToken = (session as unknown as { accessToken?: string })?.accessToken;

  const headers = new Headers(options.headers as HeadersInit);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(path, { ...options, headers });

  // If the backend rejects the token (expired or invalid), sign the user out
  // so they are redirected to /login rather than seeing silent data failures.
  // Skip this when already on /login to avoid a redirect loop.
  if (
    (response.status === 401 || response.status === 403) &&
    typeof window !== "undefined" &&
    !window.location.pathname.startsWith("/login")
  ) {
    await signOut({ callbackUrl: "/login" });
  }

  return response;
}
