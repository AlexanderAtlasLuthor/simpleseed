"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";

export default function Navbar() {
  const pathname = usePathname();
  const { data: session } = useSession();

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
          <Link href="/" className={linkClass("/")}>
            Analyze
          </Link>
          <Link href="/history" className={linkClass("/history")}>
            History
          </Link>
          <Link href="/knowledge" className={linkClass("/knowledge")}>
            Knowledge
          </Link>

          {/* User info + sign-out — only shown when authenticated */}
          {session?.user && (
            <div className="flex items-center gap-3 border-l border-[#1e2d22] pl-6">
              <span className="text-xs text-[#6b8f72] hidden sm:block truncate max-w-[160px]">
                {session.user.email}
              </span>
              <button
                onClick={() => signOut({ callbackUrl: "/login" })}
                className="text-xs text-[#6b8f72] hover:text-red-400 transition-colors"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
