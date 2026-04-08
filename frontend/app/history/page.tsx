"use client";
import { useEffect, useState } from "react";
import RFPCard from "../components/RFPCard";
import { apiFetch } from "../../lib/api";

interface RFPSummary {
  id: string;
  filename: string;
  score: number;
  decision: string;
  summary?: string;
  created_at: string;
}

export default function HistoryPage() {
  const [rfps, setRfps] = useState<RFPSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/api/rfps")
      .then((r) => r.json())
      .then(setRfps)
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this RFP analysis?")) return;
    await apiFetch(`/api/rfps/${id}`, { method: "DELETE" });
    setRfps((prev) => prev.filter((r) => r.id !== id));
  };

  const bidCount = rfps.filter((r) => r.decision === "BID").length;
  const avgScore =
    rfps.length > 0
      ? Math.round(rfps.reduce((a, r) => a + r.score, 0) / rfps.length)
      : 0;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#e8f5eb] mb-1">History</h1>
        <p className="text-sm text-[#6b8f72]">All analyzed RFPs</p>
      </div>

      {/* Stats */}
      {rfps.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Total Analyzed", value: rfps.length },
            { label: "Bid Recommendations", value: bidCount },
            { label: "Average Score", value: avgScore },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="rounded-xl border border-[#1e2d22] bg-[#111a14] p-4 text-center"
            >
              <div className="text-2xl font-bold font-mono text-seed-400">{value}</div>
              <div className="text-xs text-[#6b8f72] mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="text-center py-16 text-[#6b8f72]">Loading...</div>
      ) : rfps.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-4">📭</div>
          <p className="text-[#6b8f72]">No RFPs analyzed yet.</p>
          <a href="/" className="mt-4 inline-block text-sm text-seed-400 hover:underline">
            Analyze your first RFP →
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          {rfps.map((rfp) => (
            <RFPCard key={rfp.id} {...rfp} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
