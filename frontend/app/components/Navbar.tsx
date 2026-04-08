"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogoMark, SettingsIcon, UserIcon, ClockIcon, DatabaseIcon, ChartBarIcon, FileTextIcon } from "./Icons";

const NAV = [
  { href: "/analyze",  label: "Analyze",   Icon: FileTextIcon  },
  { href: "/history",  label: "History",   Icon: ClockIcon     },
  { href: "/knowledge",label: "Knowledge", Icon: DatabaseIcon  },
  { href: "/metrics",  label: "Metrics",   Icon: ChartBarIcon  },
];

export default function Navbar() {
  const pathname = usePathname();

  const active = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  return (
    <nav className="border-b border-[#27272a] bg-[#09090b]/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between gap-8">

        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <LogoMark className="h-7 w-7" />
          <span className="font-semibold text-[#fafafa] tracking-tight text-sm">
            SimpleSeed
          </span>
        </Link>

        {/* Main links */}
        <div className="flex items-center gap-1">
          {NAV.map(({ href, label, Icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                active(href)
                  ? "bg-[#18181b] text-[#fafafa]"
                  : "text-[#71717a] hover:text-[#fafafa] hover:bg-[#18181b]"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </Link>
          ))}
        </div>

        {/* Right — Settings + Profile */}
        <div className="flex items-center gap-1 shrink-0">
          <Link
            href="/settings"
            title="Settings"
            className={`p-2 rounded-lg transition-colors ${
              active("/settings")
                ? "bg-[#18181b] text-[#fafafa]"
                : "text-[#71717a] hover:text-[#fafafa] hover:bg-[#18181b]"
            }`}
          >
            <SettingsIcon className="h-4 w-4" />
          </Link>
          <Link
            href="/profile"
            title="Profile"
            className={`p-2 rounded-lg transition-colors ${
              active("/profile")
                ? "bg-[#18181b] text-[#fafafa]"
                : "text-[#71717a] hover:text-[#fafafa] hover:bg-[#18181b]"
            }`}
          >
            <UserIcon className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </nav>
  );
}
