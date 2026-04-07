"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ScoreCard from "../../components/ScoreCard";
import RequirementsView from "../../components/RequirementsView";
import ProposalView from "../../components/ProposalView";

type Tab = "requirements" | "proposal" | "score";

interface Analysis {
  id: string;
  filename: string;
  status: string;           // "processing" | "completed" | "partial_failure"
  completed_steps: string[];
  failed_step: string | null;
  error: { type: string; message: string } | null;
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

const PIPELINE_STEPS = [
  { id: "requirement_extraction", label: "Extracting requirements", icon: "🔍" },
  { id: "proposal_generation",    label: "Generating proposal draft", icon: "✍️" },
  { id: "bid_scoring",            label: "Scoring bid",              icon: "📊" },
];

const POLL_INTERVAL_MS = 1500;

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function PipelineProgress({ completedSteps, failedStep }: {
  completedSteps: string[];
  failedStep: string | null;
}) {
  return (
    <div className="max-w-md mx-auto px-6 py-16">
      <div className="flex items-center justify-center gap-3 mb-10 text-[#6b8f72]">
        <Spinner className="h-5 w-5" />
        <span className="text-sm font-medium">Analyzing RFP…</span>
      </div>

      <div className="space-y-3">
        {PIPELINE_STEPS.map((step, i) => {
          const done    = completedSteps.includes(step.id);
          const failed  = failedStep === step.id;
          const active  = !done && !failed && completedSteps.length === i;
          const waiting = !done && !failed && !active;

          return (
            <div
              key={step.id}
              className={`flex items-center gap-4 px-5 py-4 rounded-xl border transition-colors ${
                done    ? "border-seed-800 bg-seed-900/20 text-seed-400"
                : failed  ? "border-red-900 bg-red-950/20 text-red-400"
                : active  ? "border-[#1e3022] bg-[#0d1610] text-[#e8f5eb]"
                :            "border-[#111a14] bg-transparent text-[#2d4433]"
              }`}
            >
              {/* Status icon */}
              <div className="w-5 flex items-center justify-center shrink-0">
                {done    ? <span className="text-seed-400 font-bold text-sm">✓</span>
                : failed  ? <span className="text-red-400 text-sm">✗</span>
                : active  ? <Spinner className="h-4 w-4 text-[#6b8f72]" />
                :            <span className="text-[#2d4433] text-xs">○</span>}
              </div>

              {/* Label */}
              <span className="text-sm font-medium flex-1">
                {step.icon} {step.label}
              </span>

              {/* Trailing badge */}
              {done   && <span className="text-xs text-seed-700 shrink-0">done</span>}
              {active && <span className="text-xs text-[#6b8f72] animate-pulse shrink-0">running…</span>}
              {failed && <span className="text-xs text-red-600 shrink-0">failed</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Analysis | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("score");
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) clearTimeout(pollingRef.current);
  }, []);

  const poll = useCallback(async () => {
    try {
      const r = await fetch(`/api/rfps/${id}`);
      if (!r.ok) {
        setFetchError("Analysis not found");
        return;
      }
      const json: Analysis = await r.json();
      setData(json);

      if (json.status === "processing") {
        pollingRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    } catch {
      setFetchError("Could not reach the server");
    }
  }, [id]);

  useEffect(() => {
    poll();
    return stopPolling;
  }, [poll, stopPolling]);

  // ── Still fetching first response ─────────────────────────────────────────
  if (!data && !fetchError) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-[#6b8f72]">
          <Spinner className="h-5 w-5" />
          <span className="text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  // ── Fetch error (404, network) ─────────────────────────────────────────────
  if (fetchError || !data) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-20 text-center">
        <p className="text-red-400 mb-4">{fetchError || "Analysis not found"}</p>
        <button onClick={() => router.push("/")} className="text-sm text-seed-400 hover:underline">
          ← Back to home
        </button>
      </div>
    );
  }

  // ── Pipeline running — show per-step progress ─────────────────────────────
  if (data.status === "processing") {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        <button
          onClick={() => router.push("/")}
          className="text-xs text-[#6b8f72] hover:text-seed-400 transition-colors mb-6 flex items-center gap-1"
        >
          ← New analysis
        </button>
        <h1 className="text-lg font-semibold text-[#e8f5eb] truncate mb-1">{data.filename}</h1>
        <PipelineProgress
          completedSteps={data.completed_steps ?? []}
          failedStep={null}
        />
      </div>
    );
  }

  // ── Partial failure — show error and retry hint ───────────────────────────
  if (data.status === "partial_failure") {
    const stepLabel = PIPELINE_STEPS.find(s => s.id === data.failed_step)?.label ?? data.failed_step;
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        <button
          onClick={() => router.push("/")}
          className="text-xs text-[#6b8f72] hover:text-seed-400 transition-colors mb-6 flex items-center gap-1"
        >
          ← New analysis
        </button>
        <h1 className="text-lg font-semibold text-[#e8f5eb] truncate mb-6">{data.filename}</h1>

        <PipelineProgress
          completedSteps={data.completed_steps ?? []}
          failedStep={data.failed_step}
        />

        <div className="max-w-md mx-auto mt-4 p-4 rounded-xl bg-red-950/30 border border-red-900/50">
          <p className="text-sm text-red-300 mb-1 font-medium">
            Pipeline failed at: {stepLabel}
          </p>
          {data.error?.message && (
            <p className="text-xs text-red-400/70 mt-1">{data.error.message}</p>
          )}
          <button
            onClick={async () => {
              await fetch(`/api/rfps/${id}/retry`, { method: "POST" });
              poll();
            }}
            className="mt-3 text-xs px-3 py-1.5 rounded-lg bg-seed-900/40 border border-seed-800/50 text-seed-400 hover:bg-seed-900/60 transition-colors"
          >
            ↻ Retry from failed step
          </button>
        </div>
      </div>
    );
  }

  // ── Completed — full result view ──────────────────────────────────────────
  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "score",        label: "Score",        icon: "📊" },
    { id: "requirements", label: "Requirements", icon: "🔍" },
    { id: "proposal",     label: "Proposal",     icon: "✍️" },
  ];

  const date = new Date(data.created_at).toLocaleDateString("en-US", {
    month: "long", day: "numeric", year: "numeric",
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
            <h1 className="text-2xl font-bold text-[#e8f5eb] truncate max-w-lg">{data.filename}</h1>
            <p className="text-sm text-[#6b8f72] mt-1">{date}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`px-3 py-1.5 rounded-full text-sm font-semibold ${
              data.score.decision === "BID"
                ? "bg-seed-900/50 text-seed-400 border border-seed-800"
                : "bg-red-950/50 text-red-400 border border-red-900"
            }`}>
              {data.score.decision}
            </span>
            <span className="text-2xl font-bold font-mono text-[#e8f5eb]">{data.score.score}</span>
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
    </div>
  );
}
