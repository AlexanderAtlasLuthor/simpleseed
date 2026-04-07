"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    // Mock: just redirect after a short delay
    await new Promise((r) => setTimeout(r, 600));
    router.push("/analyze");
  };

  return (
    <div className="min-h-[calc(100vh-56px)] flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <Link href="/" className="inline-flex items-center gap-2 mb-6">
            <span className="text-seed-500 text-3xl">🌱</span>
            <span className="text-2xl font-bold text-[#e8f5eb] tracking-tight">SimpleSeed</span>
          </Link>
          <h1 className="text-xl font-semibold text-[#e8f5eb]">Welcome back</h1>
          <p className="text-sm text-[#6b8f72] mt-1">Sign in to your account</p>
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs text-[#6b8f72] mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full bg-[#0d1610] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-[#6b8f72] mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-[#0d1610] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
            />
          </div>

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" className="rounded border-[#1e2d22] bg-[#0d1610] accent-seed-500" />
              <span className="text-xs text-[#6b8f72]">Remember me</span>
            </label>
            <button type="button" className="text-xs text-seed-400 hover:text-seed-300 transition-colors">
              Forgot password?
            </button>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-seed-600 hover:bg-seed-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>
        </form>

        <p className="text-center text-xs text-[#6b8f72] mt-6">
          Don&apos;t have an account?{" "}
          <button
            onClick={() => router.push("/analyze")}
            className="text-seed-400 hover:text-seed-300 transition-colors"
          >
            Get started free
          </button>
        </p>
      </div>
    </div>
  );
}
