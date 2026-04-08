"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import RFPCard from "../components/RFPCard";
import { InboxIcon } from "../components/Icons";

interface RFPSummary {
  id: string;
  filename: string;
  score: number;
  decision: string;
  summary?: string;
  created_at: string;
}

export default function HistoryPage() {
  const [rfps, setRfps]       = useState<RFPSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/rfps").then((r) => r.json()).then(setRfps).finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this RFP analysis?")) return;
    await fetch(`/api/rfps/${id}`, { method: "DELETE" });
    setRfps((prev) => prev.filter((r) => r.id !== id));
  };

  const bidCount = rfps.filter((r) => r.decision === "BID").length;
  const avgScore = rfps.length > 0
    ? Math.round(rfps.reduce((a, r) => a + r.score, 0) / rfps.length)
    : 0;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#fafafa] mb-1">History</h1>
        <p className="text-sm text-[#71717a]">All analyzed RFPs</p>
      </div>

      {rfps.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Total Analyzed",      value: rfps.length },
            { label: "BID Recommendations", value: bidCount    },
            { label: "Average Score",        value: avgScore    },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-xl border border-[#27272a] bg-[#111113] p-4 text-center">
              <div className="text-2xl font-bold font-mono text-seed-400">{value}</div>
              <div className="text-xs text-[#71717a] mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="text-center py-16 text-[#71717a] text-sm">Loading…</div>
      ) : rfps.length === 0 ? (
        <div className="text-center py-20">
          <div className="flex justify-center mb-4">
            <InboxIcon className="h-10 w-10 text-[#3f3f46]" />
          </div>
          <p className="text-[#71717a] text-sm mb-4">No RFPs analyzed yet.</p>
          <Link href="/analyze" className="text-sm text-seed-400 hover:text-seed-300 transition-colors">
            Analyze your first RFP
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {rfps.map((rfp) => <RFPCard key={rfp.id} {...rfp} onDelete={handleDelete} />)}
        </div>
      )}
    </div>
  );
}
