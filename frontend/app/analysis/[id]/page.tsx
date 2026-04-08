"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ScoreCard from "../../components/ScoreCard";
import RequirementsView from "../../components/RequirementsView";
import ProposalView from "../../components/ProposalView";
import {
  SpinnerIcon, CheckIcon, XIcon, SearchIcon, PencilIcon,
  ChartBarIcon, ArrowLeftIcon, RefreshIcon, DownloadIcon,
} from "../../components/Icons";

type Tab = "requirements" | "proposal" | "score";

interface Analysis {
  id: string;
  filename: string;
  status: string;
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
  { id: "requirement_extraction", label: "Extracting requirements",  Icon: SearchIcon   },
  { id: "proposal_generation",    label: "Generating proposal draft", Icon: PencilIcon   },
  { id: "bid_scoring",            label: "Scoring bid",               Icon: ChartBarIcon },
];

const POLL_INTERVAL_MS = 1500;

function PipelineProgress({ completedSteps, failedStep }: {
  completedSteps: string[];
  failedStep: string | null;
}) {
  return (
    <div className="max-w-md mx-auto px-6 py-16">
      <div className="flex items-center justify-center gap-3 mb-10 text-[#71717a]">
        <SpinnerIcon className="h-5 w-5" />
        <span className="text-sm font-medium">Analyzing RFP…</span>
      </div>

      <div className="space-y-2">
        {PIPELINE_STEPS.map(({ id, label, Icon }, i) => {
          const done    = completedSteps.includes(id);
          const failed  = failedStep === id;
          const active  = !done && !failed && completedSteps.length === i;
          const waiting = !done && !failed && !active;

          return (
            <div
              key={id}
              className={`flex items-center gap-4 px-4 py-3.5 rounded-xl border transition-colors ${
                done    ? "border-[#1e3a8a] bg-seed-950/30 text-seed-400"
                : failed  ? "border-red-900 bg-red-950/20 text-red-400"
                : active  ? "border-[#27272a] bg-[#18181b] text-[#fafafa]"
                :            "border-[#1c1c1f] bg-transparent text-[#3f3f46]"
              }`}
            >
              <div className="w-5 flex items-center justify-center shrink-0">
                {done   ? <CheckIcon className="h-4 w-4 text-seed-400" />
                : failed  ? <XIcon className="h-4 w-4 text-red-400" />
                : active  ? <SpinnerIcon className="h-4 w-4 text-[#71717a]" />
                :            <div className="h-1.5 w-1.5 rounded-full bg-[#3f3f46]" />}
              </div>
              <Icon className="h-4 w-4 shrink-0 opacity-60" />
              <span className="text-sm font-medium flex-1">{label}</span>
              {done    && <span className="text-xs text-[#52525b] shrink-0">done</span>}
              {active  && <span className="text-xs text-[#71717a] animate-pulse shrink-0">running</span>}
              {failed  && <span className="text-xs text-red-600 shrink-0">failed</span>}
              {waiting && <span className="text-xs text-[#3f3f46] shrink-0">waiting</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const router  = useRouter();
  const [data, setData]             = useState<Analysis | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeTab, setActiveTab]   = useState<Tab>("score");
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) clearTimeout(pollingRef.current);
  }, []);

  const poll = useCallback(async () => {
    try {
      const r = await fetch(`/api/rfps/${id}`);
      if (!r.ok) { setFetchError("Analysis not found"); return; }
      const json: Analysis = await r.json();
      setData(json);
      if (json.status === "processing") {
        pollingRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    } catch {
      setFetchError("Could not reach the server");
    }
  }, [id]);

  useEffect(() => { poll(); return stopPolling; }, [poll, stopPolling]);

  const backBtn = (
    <button
      onClick={() => router.push("/")}
      className="flex items-center gap-1.5 text-xs text-[#71717a] hover:text-[#fafafa] transition-colors mb-6"
    >
      <ArrowLeftIcon className="h-3.5 w-3.5" />
      New analysis
    </button>
  );

  if (!data && !fetchError) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-[#71717a]">
          <SpinnerIcon className="h-5 w-5" />
          <span className="text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  if (fetchError || !data) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-20 text-center">
        <p className="text-red-400 mb-4">{fetchError || "Analysis not found"}</p>
        <button onClick={() => router.push("/")} className="text-sm text-seed-400 hover:underline">
          Back to home
        </button>
      </div>
    );
  }

  if (data.status === "processing") {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        {backBtn}
        <h1 className="text-lg font-semibold text-[#fafafa] truncate mb-1">{data.filename}</h1>
        <PipelineProgress completedSteps={data.completed_steps ?? []} failedStep={null} />
      </div>
    );
  }

  if (data.status === "partial_failure") {
    const stepLabel = PIPELINE_STEPS.find(s => s.id === data.failed_step)?.label ?? data.failed_step;
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        {backBtn}
        <h1 className="text-lg font-semibold text-[#fafafa] truncate mb-6">{data.filename}</h1>
        <PipelineProgress completedSteps={data.completed_steps ?? []} failedStep={data.failed_step} />
        <div className="max-w-md mx-auto mt-4 p-4 rounded-xl bg-red-950/30 border border-red-900/50">
          <p className="text-sm text-red-300 mb-1 font-medium">Failed at: {stepLabel}</p>
          {data.error?.message && (
            <p className="text-xs text-red-400/70 mt-1">{data.error.message}</p>
          )}
          <button
            onClick={async () => { await fetch(`/api/rfps/${id}/retry`, { method: "POST" }); poll(); }}
            className="mt-3 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-[#71717a] hover:text-[#fafafa] transition-colors"
          >
            <RefreshIcon className="h-3.5 w-3.5" />
            Retry from failed step
          </button>
        </div>
      </div>
    );
  }

  const tabs: { id: Tab; label: string; Icon: typeof SearchIcon }[] = [
    { id: "score",        label: "Score",        Icon: ChartBarIcon },
    { id: "requirements", label: "Requirements", Icon: SearchIcon   },
    { id: "proposal",     label: "Proposal",     Icon: PencilIcon   },
  ];

  const date = new Date(data.created_at).toLocaleDateString("en-US", {
    month: "long", day: "numeric", year: "numeric",
  });

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        {backBtn}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#fafafa] truncate max-w-lg">{data.filename}</h1>
            <p className="text-sm text-[#71717a] mt-1">{date}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            <a
              href={`/api/rfps/${data.id}/export/pdf`}
              download
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-[#27272a] bg-[#18181b] text-[#71717a] hover:text-[#fafafa] hover:border-[#3f3f46] transition-colors"
            >
              <DownloadIcon className="h-3.5 w-3.5" />
              PDF
            </a>
            <a
              href={`/api/rfps/${data.id}/export/docx`}
              download
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-[#27272a] bg-[#18181b] text-[#71717a] hover:text-[#fafafa] hover:border-[#3f3f46] transition-colors"
            >
              <DownloadIcon className="h-3.5 w-3.5" />
              Word
            </a>
            <span className={`px-3 py-1.5 rounded-lg text-sm font-semibold ${
              data.score.decision === "BID"
                ? "bg-seed-950/60 text-seed-400 border border-seed-900"
                : "bg-red-950/50 text-red-400 border border-red-900"
            }`}>
              {data.score.decision}
            </span>
            <span className="text-2xl font-bold font-mono text-[#fafafa]">{data.score.score}</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[#111113] border border-[#1c1c1f] mb-6">
        {tabs.map(({ id: tabId, label, Icon }) => (
          <button
            key={tabId}
            onClick={() => setActiveTab(tabId)}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tabId
                ? "bg-[#18181b] text-[#fafafa] border border-[#27272a]"
                : "text-[#71717a] hover:text-[#fafafa]"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {activeTab === "score"        && <ScoreCard score={data.score} />}
      {activeTab === "requirements" && (
        <RequirementsView requirements={data.requirements as Parameters<typeof RequirementsView>[0]["requirements"]} />
      )}
      {activeTab === "proposal" && <ProposalView proposal={data.proposal} />}
    </div>
  );
}
