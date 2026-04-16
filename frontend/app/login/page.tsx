"use client";
import { useState, FormEvent } from "react";
import Link from "next/link";
import { setToken } from "../../lib/api";

export default function LoginPage() {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // OAuth2 password flow requires form-urlencoded, not JSON
      const body = new URLSearchParams();
      body.append("username", email);
      body.append("password", password);

      const res = await fetch("http://localhost:8000/api/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Login failed (${res.status})`);
      }

      const data = await res.json();
      setToken(data.access_token);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-[#e8f5eb] mb-2">Sign in</h1>
        <p className="text-sm text-[#6b8f72] mb-8">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-seed-400 hover:underline">
            Register
          </Link>
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs text-[#6b8f72] mb-1" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-[#1e2d22] bg-[#0f1a12] px-3 py-2 text-sm text-[#e8f5eb] focus:outline-none focus:ring-1 focus:ring-seed-500"
            />
          </div>

          <div>
            <label className="block text-xs text-[#6b8f72] mb-1" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-[#1e2d22] bg-[#0f1a12] px-3 py-2 text-sm text-[#e8f5eb] focus:outline-none focus:ring-1 focus:ring-seed-500"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/50 rounded px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="rounded bg-seed-600 hover:bg-seed-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
