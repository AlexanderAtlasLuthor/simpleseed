"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, clearToken } from "../../lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const router   = useRouter();
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  // Check auth state on mount and when the route changes
  useEffect(() => {
    setIsLoggedIn(!!getToken());
  }, [pathname]);

  function handleLogout() {
    clearToken();
    setIsLoggedIn(false);
    router.push("/login");
  }

  const linkClass = (href: string) =>
    `text-sm font-medium transition-colors ${
      pathname === href
        ? "text-seed-400"
        : "text-[#6b8f72] hover:text-[#e8f5eb]"
    }`;

  return (
    <nav className="border-b border-[#1e2d22] bg-[#0a0f0d]/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-seed-500 text-xl">🌱</span>
          <span className="font-semibold text-[#e8f5eb] tracking-tight">
            SimpleSeed
          </span>
        </Link>

        <div className="flex items-center gap-6">
          {isLoggedIn ? (
            <>
              <Link href="/" className={linkClass("/")}>
                Analyze
              </Link>
              <Link href="/history" className={linkClass("/history")}>
                History
              </Link>
              <Link href="/knowledge" className={linkClass("/knowledge")}>
                Knowledge
              </Link>
              <button
                onClick={handleLogout}
                className="text-sm font-medium text-[#6b8f72] hover:text-[#e8f5eb] transition-colors"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className={linkClass("/login")}>
                Sign in
              </Link>
              <Link
                href="/register"
                className="text-sm font-medium rounded bg-seed-700 hover:bg-seed-600 px-3 py-1.5 text-[#e8f5eb] transition-colors"
              >
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
