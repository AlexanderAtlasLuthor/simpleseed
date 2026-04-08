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
 */
import { getSession } from "next-auth/react";

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

  return fetch(path, { ...options, headers });
}
