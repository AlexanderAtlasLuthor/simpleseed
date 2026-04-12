"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ScoreCard from "../../components/ScoreCard";
import RequirementsView from "../../components/RequirementsView";
import ProposalView from "../../components/ProposalView";
import FeedbackPanel from "../../components/FeedbackPanel";

type Tab = "requirements" | "proposal" | "score";

interface Analysis {
  id: string;
  filename: string;
  requirements: Record<string, unknown>;
  proposal: string;
  score: {
    score: number;
    decision: string;
    breakdown: Record<string, number>;
    reasoning: string;
  };
  created_at: string;
}

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("score");

  useEffect(() => {
    fetch(`/api/rfps/${id}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-[#6b8f72]">
          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading analysis...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-20 text-center">
        <p className="text-red-400 mb-4">{error || "Analysis not found"}</p>
        <button
          onClick={() => router.push("/")}
          className="text-sm text-seed-400 hover:underline"
        >
          ← Back to home
        </button>
      </div>
    );
  }

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "score", label: "Score", icon: "📊" },
    { id: "requirements", label: "Requirements", icon: "🔍" },
    { id: "proposal", label: "Proposal", icon: "✍️" },
  ];

  const date = new Date(data.created_at).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <button
          onClick={() => router.push("/")}
          className="text-xs text-[#6b8f72] hover:text-seed-400 transition-colors mb-4 flex items-center gap-1"
        >
          ← New analysis
        </button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#e8f5eb] truncate max-w-lg">
              {data.filename}
            </h1>
            <p className="text-sm text-[#6b8f72] mt-1">{date}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span
              className={`px-3 py-1.5 rounded-full text-sm font-semibold ${
                data.score.decision === "BID"
                  ? "bg-seed-900/50 text-seed-400 border border-seed-800"
                  : "bg-red-950/50 text-red-400 border border-red-900"
              }`}
            >
              {data.score.decision}
            </span>
            <span className="text-2xl font-bold font-mono text-[#e8f5eb]">
              {data.score.score}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[#111a14] border border-[#1e2d22] mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.id
                ? "bg-seed-900/60 text-seed-400 border border-seed-800/50"
                : "text-[#6b8f72] hover:text-[#e8f5eb]"
            }`}
          >
            <span>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {activeTab === "score" && <ScoreCard score={data.score} />}
      {activeTab === "requirements" && (
        <RequirementsView requirements={data.requirements as Parameters<typeof RequirementsView>[0]["requirements"]} />
      )}
      {activeTab === "proposal" && <ProposalView proposal={data.proposal} />}

      {/* Feedback panel — always visible below tabs */}
      <FeedbackPanel rfpId={data.id} />
    </div>
  );
}
