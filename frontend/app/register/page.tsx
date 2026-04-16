"use client";
import { useState, FormEvent } from "react";
import Link from "next/link";
import { setToken } from "../../lib/api";

export default function RegisterPage() {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm]   = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Registration failed (${res.status})`);
      }

      const data = await res.json();
      setToken(data.access_token);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-[#e8f5eb] mb-2">Create account</h1>
        <p className="text-sm text-[#6b8f72] mb-8">
          Already have an account?{" "}
          <Link href="/login" className="text-seed-400 hover:underline">
            Sign in
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
              <span className="ml-1 text-[#4a6b52]">(min 8 characters)</span>
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-[#1e2d22] bg-[#0f1a12] px-3 py-2 text-sm text-[#e8f5eb] focus:outline-none focus:ring-1 focus:ring-seed-500"
            />
          </div>

          <div>
            <label className="block text-xs text-[#6b8f72] mb-1" htmlFor="confirm">
              Confirm password
            </label>
            <input
              id="confirm"
              type="password"
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
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
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
