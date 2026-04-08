"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogoMark, MailIcon, LockIcon, SpinnerIcon } from "../components/Icons";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading]   = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    await new Promise((r) => setTimeout(r, 600));
    router.push("/analyze");
  };

  return (
    <div className="min-h-[calc(100vh-56px)] flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-10">
          <Link href="/" className="inline-flex items-center gap-2.5 mb-6">
            <LogoMark className="h-9 w-9" />
            <span className="text-xl font-bold text-[#fafafa] tracking-tight">SimpleSeed</span>
          </Link>
          <h1 className="text-xl font-semibold text-[#fafafa]">Sign in to your account</h1>
          <p className="text-sm text-[#71717a] mt-1">RFP Intelligence Platform</p>
        </div>

        {/* Card */}
        <div className="bg-[#111113] border border-[#27272a] rounded-2xl p-6">
          <form onSubmit={handleLogin} className="space-y-4">

            <div>
              <label className="block text-xs text-[#71717a] mb-1.5 font-medium">
                Email address
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center">
                  <MailIcon className="h-4 w-4 text-[#52525b]" />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full bg-[#18181b] border border-[#27272a] rounded-xl pl-10 pr-4 py-2.5 text-sm text-[#fafafa] placeholder-[#52525b] focus:outline-none focus:border-seed-700 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs text-[#71717a] mb-1.5 font-medium">
                Password
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center">
                  <LockIcon className="h-4 w-4 text-[#52525b]" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-[#18181b] border border-[#27272a] rounded-xl pl-10 pr-4 py-2.5 text-sm text-[#fafafa] placeholder-[#52525b] focus:outline-none focus:border-seed-700 transition-colors"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" className="rounded border-[#27272a] bg-[#18181b] accent-seed-500" />
                <span className="text-xs text-[#71717a]">Remember me</span>
              </label>
              <button type="button" className="text-xs text-seed-400 hover:text-seed-300 transition-colors">
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-seed-600 hover:bg-seed-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors flex items-center justify-center gap-2 mt-2"
            >
              {loading
                ? <><SpinnerIcon className="h-4 w-4" /> Signing in…</>
                : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[#52525b] mt-5">
          Don&apos;t have an account?{" "}
          <button
            onClick={() => router.push("/analyze")}
            className="text-seed-400 hover:text-seed-300 transition-colors"
          >
            Try without signing in
          </button>
        </p>
      </div>
    </div>
  );
}
