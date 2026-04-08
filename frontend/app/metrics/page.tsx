"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

interface RFPSummary {
  id: string;
  filename: string;
  score: number;
  decision: string;
  industry: string;
  status: string;
  created_at: string;
}

function StatCard({ label, value, sub, accent }: {
  label: string; value: string | number; sub?: string; accent?: boolean;
}) {
  return (
    <div className="p-6 rounded-xl border border-[#27272a] bg-[#111113]">
      <div className="text-xs text-[#71717a] mb-2">{label}</div>
      <div className={`text-3xl font-bold font-mono ${accent ? "text-seed-400" : "text-[#fafafa]"}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-[#52525b] mt-1">{sub}</div>}
    </div>
  );
}

const BUCKETS = [
  { label: "0–20",   min: 0,  max: 20  },
  { label: "21–40",  min: 21, max: 40  },
  { label: "41–60",  min: 41, max: 60  },
  { label: "61–80",  min: 61, max: 80  },
  { label: "81–100", min: 81, max: 100 },
];

export default function MetricsPage() {
  const [rfps, setRfps]       = useState<RFPSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/rfps")
      .then((r) => r.json())
      .then((data) => setRfps(Array.isArray(data) ? data : []))
      .catch(() => setRfps([]))
      .finally(() => setLoading(false));
  }, []);

  const completed = rfps.filter((r) => r.status === "completed");
  const bids      = completed.filter((r) => r.decision === "BID");
  const noBids    = completed.filter((r) => r.decision === "NO BID");
  const bidRate   = completed.length > 0 ? Math.round((bids.length / completed.length) * 100) : 0;
  const avgScore  = completed.length > 0
    ? Math.round(completed.reduce((s, r) => s + (r.score || 0), 0) / completed.length)
    : 0;

  const now = new Date();
  const thisMonth = completed.filter((r) => {
    const d = new Date(r.created_at);
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  });

  const bucketCounts = BUCKETS.map((b) =>
    completed.filter((r) => r.score >= b.min && r.score <= b.max).length
  );
  const maxBucket = Math.max(...bucketCounts, 1);

  const recent = [...rfps]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 8);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-[#71717a] text-sm">
        Loading metrics…
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#fafafa]">Metrics</h1>
        <p className="text-sm text-[#71717a] mt-1">Overview of your RFP pipeline</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total analyses"  value={rfps.length}    sub={`${completed.length} completed`} />
        <StatCard label="BID rate"        value={`${bidRate}%`}  sub={`${bids.length} BID / ${noBids.length} NO BID`} accent />
        <StatCard label="Average score"   value={avgScore}       sub="completed analyses" />
        <StatCard label="This month"      value={thisMonth.length} sub="analyses submitted" />
      </div>

      {/* Score distribution */}
      {completed.length > 0 && (
        <div className="p-6 rounded-xl border border-[#27272a] bg-[#111113] mb-8">
          <h2 className="text-sm font-semibold text-[#fafafa] mb-6">Score distribution</h2>
          <div className="flex items-end gap-3 h-28">
            {BUCKETS.map((b, i) => (
              <div key={b.label} className="flex-1 flex flex-col items-center gap-2">
                <div className="text-xs text-[#71717a]">{bucketCounts[i]}</div>
                <div
                  className="w-full rounded-t bg-seed-900/50 border border-seed-800/30 transition-all"
                  style={{
                    height: `${Math.round((bucketCounts[i] / maxBucket) * 80)}px`,
                    minHeight: bucketCounts[i] > 0 ? "4px" : "0",
                  }}
                />
                <div className="text-xs text-[#52525b] whitespace-nowrap">{b.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent analyses */}
      <div className="p-6 rounded-xl border border-[#27272a] bg-[#111113]">
        <h2 className="text-sm font-semibold text-[#fafafa] mb-4">Recent analyses</h2>
        {recent.length === 0 ? (
          <div className="text-center py-10">
            <p className="text-sm text-[#71717a] mb-4">No analyses yet.</p>
            <Link href="/analyze" className="text-sm text-seed-400 hover:text-seed-300 transition-colors">
              Analyze your first RFP
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-[#1c1c1f]">
            {recent.map((rfp) => (
              <div key={rfp.id} className="py-3 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <Link href={`/analysis/${rfp.id}`}
                    className="text-sm text-[#fafafa] hover:text-seed-400 transition-colors truncate block">
                    {rfp.filename}
                  </Link>
                  <div className="text-xs text-[#71717a] mt-0.5">
                    {new Date(rfp.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    {rfp.industry && rfp.industry !== "general" && (
                      <span className="ml-2 capitalize">{rfp.industry.replace("_", " ")}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {rfp.status === "completed" && (
                    <>
                      <span className={`px-2 py-0.5 rounded-lg text-xs font-medium border ${
                        rfp.decision === "BID"
                          ? "bg-seed-950/50 text-seed-400 border-seed-900"
                          : "bg-red-950/50 text-red-400 border-red-900"
                      }`}>
                        {rfp.decision}
                      </span>
                      <span className="text-sm font-mono font-bold text-[#fafafa] w-8 text-right">
                        {rfp.score}
                      </span>
                    </>
                  )}
                  {rfp.status === "processing"      && <span className="text-xs text-[#71717a]">processing…</span>}
                  {rfp.status === "partial_failure" && <span className="text-xs text-red-400">failed</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
