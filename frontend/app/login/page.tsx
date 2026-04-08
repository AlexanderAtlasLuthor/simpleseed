"use client";
import { useState, FormEvent } from "react";
import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // After login, redirect to the page the user tried to visit (default: home).
  // Validate callbackUrl to prevent open redirect attacks.
  // Only allow relative paths that start with "/" but not "//".
  const _rawCallback = searchParams.get("callbackUrl") ?? "/";
  const callbackUrl =
    _rawCallback.startsWith("/") && !_rawCallback.startsWith("//")
      ? _rawCallback
      : "/";

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    if (mode === "register") {
      // Call FastAPI backend directly using an absolute URL so Next.js route
      // handlers (NextAuth's catch-all) cannot intercept the request.
      try {
        const backendUrl =
          process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const res = await fetch(`${backendUrl}/api/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        const data = await res.json();
        if (!res.ok) {
          setError(data.detail ?? "Registration failed.");
          setLoading(false);
          return;
        }
      } catch {
        setError("Could not reach the server. Is the backend running?");
        setLoading(false);
        return;
      }
    }

    // For both login and post-registration, authenticate with NextAuth.
    const result = await signIn("credentials", {
      email,
      password,
      redirect: false, // handle redirect manually so we can show errors
    });

    if (result?.error) {
      setError("Incorrect email or password.");
      setLoading(false);
      return;
    }

    router.push(callbackUrl);
    router.refresh(); // re-render server components with the new session
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2 justify-center">
            <span className="text-seed-500 text-3xl">🌱</span>
            <span className="font-semibold text-2xl text-[#e8f5eb] tracking-tight">
              SimpleSeed
            </span>
          </Link>
          <p className="mt-2 text-sm text-[#6b8f72]">
            {mode === "login" ? "Sign in to your account" : "Create a new account"}
          </p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-[#1e2d22] bg-[#111a14] p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-[#6b8f72] mb-1.5">Email</label>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-[#0a0f0d] border border-[#1e2d22] rounded-xl px-4 py-2.5 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label className="block text-xs text-[#6b8f72] mb-1.5">Password</label>
              <input
                type="password"
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-[#0a0f0d] border border-[#1e2d22] rounded-xl px-4 py-2.5 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
                placeholder={mode === "register" ? "Min. 8 characters" : "••••••••"}
              />
            </div>

            {error && (
              <div className="p-3 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-seed-700 hover:bg-seed-600 disabled:opacity-50 disabled:cursor-not-allowed text-[#e8f5eb] font-medium text-sm transition-colors"
            >
              {loading
                ? mode === "login"
                  ? "Signing in…"
                  : "Creating account…"
                : mode === "login"
                ? "Sign in"
                : "Create account"}
            </button>
          </form>

          {/* Mode toggle */}
          <div className="mt-6 text-center text-sm text-[#6b8f72]">
            {mode === "login" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  type="button"
                  onClick={() => { setMode("register"); setError(null); }}
                  className="text-seed-400 hover:underline"
                >
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  type="button"
                  onClick={() => { setMode("login"); setError(null); }}
                  className="text-seed-400 hover:underline"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
