"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

interface DashboardData {
  total_rfps: number;
  bid_count: number;
  no_bid_count: number;
  bid_pct: number;
  total_feedback: number;
  correct_rate: number | null;
  override_rate: number | null;
  win_rate: number | null;
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-5 flex flex-col gap-1 ${
        accent
          ? "border-seed-800 bg-seed-900/20"
          : "border-[#1e2d22] bg-[#0d1610]"
      }`}
    >
      <p className="text-xs text-[#6b8f72] uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-bold font-mono text-[#e8f5eb]">{value}</p>
      {sub && <p className="text-xs text-[#6b8f72]">{sub}</p>}
    </div>
  );
}

function pct(rate: number | null): string {
  if (rate === null) return "—";
  return `${Math.round(rate * 100)}%`;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/dashboard")
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load dashboard");
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-[#6b8f72]">
          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-20 text-center">
        <p className="text-red-400 mb-4">{error || "Failed to load dashboard"}</p>
        <Link href="/" className="text-sm text-seed-400 hover:underline">
          ← Back to home
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#e8f5eb]">Dashboard</h1>
        <p className="text-sm text-[#6b8f72] mt-1">
          Aggregate metrics across all RFP analyses
        </p>
      </div>

      {/* Pipeline volume */}
      <section className="mb-8">
        <h2 className="text-xs text-[#6b8f72] uppercase tracking-widest mb-3">
          Pipeline Volume
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="Total analyzed"
            value={String(data.total_rfps)}
            accent
          />
          <StatCard
            label="BID recommended"
            value={`${data.bid_pct}%`}
            sub={`${data.bid_count} of ${data.total_rfps}`}
          />
          <StatCard
            label="NO BID"
            value={String(data.no_bid_count)}
          />
          <StatCard
            label="Feedback recorded"
            value={String(data.total_feedback)}
          />
        </div>
      </section>

      {/* User signals */}
      <section className="mb-8">
        <h2 className="text-xs text-[#6b8f72] uppercase tracking-widest mb-3">
          User Signals
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <StatCard
            label="Agreement rate"
            value={pct(data.correct_rate)}
            sub="User marked recommendation correct"
            accent={data.correct_rate !== null}
          />
          <StatCard
            label="Override rate"
            value={pct(data.override_rate)}
            sub="User marked recommendation incorrect"
          />
          <StatCard
            label="Win rate"
            value={pct(data.win_rate)}
            sub="Won / (Won + Lost)"
            accent={data.win_rate !== null}
          />
        </div>
        {data.total_feedback === 0 && (
          <p className="mt-3 text-xs text-[#6b8f72]">
            No feedback recorded yet. Open an analysis and use the Feedback &amp; Outcome
            panel to start tracking results.
          </p>
        )}
      </section>

      <div className="flex gap-4 text-sm">
        <Link href="/" className="text-seed-400 hover:underline">
          + New analysis
        </Link>
        <Link href="/history" className="text-[#6b8f72] hover:text-[#e8f5eb]">
          View history
        </Link>
      </div>
    </div>
  );
}
