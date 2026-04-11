// 1.3 Explainable Scoring — ScoreCard
//
// Backward-compatible: all new fields (factor_details, strengths, risks,
// summary_explanation, confidence, missing_inputs) are optional so pre-1.3
// analyses that lack them still render without errors.

interface FactorDetail {
  score: number;
  weight: number;
  explanation: string;
  evidence: string;
}

interface ScoreData {
  score: number;
  decision: string;
  breakdown: {
    relevance_score?: number;
    budget_fit?: number;
    requirements_match?: number;
    completeness?: number;
  };
  reasoning: string;
  // 1.3 explainability (optional for backward compat)
  factor_details?: Record<string, FactorDetail>;
  strengths?: string[];
  risks?: string[];
  summary_explanation?: string;
  confidence?: "high" | "medium" | "low";
  missing_inputs?: string[];
}

interface Props {
  score: ScoreData;
}

const FACTORS = [
  { key: "relevance_score",    label: "Relevance",           weight: "30%" },
  { key: "budget_fit",         label: "Budget Fit",          weight: "25%" },
  { key: "requirements_match", label: "Requirements Match",  weight: "25%" },
  { key: "completeness",       label: "Completeness",        weight: "20%" },
] as const;

function ScoreBar({ value }: { value: number }) {
  const color =
    value >= 70 ? "bg-seed-500" : value >= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 bg-[#1e2d22] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs font-mono text-[#6b8f72] w-8 text-right">{value}</span>
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  if (confidence === "high") return null;
  const isLow = confidence === "low";
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full border ${
        isLow
          ? "bg-yellow-950/40 border-yellow-800/50 text-yellow-400"
          : "bg-[#111a14] border-[#1e2d22] text-[#6b8f72]"
      }`}
    >
      Confidence: {confidence}
    </span>
  );
}

export default function ScoreCard({ score }: Props) {
  const isBid       = score.decision === "BID";
  const confidence  = score.confidence ?? "medium";
  const strengths   = score.strengths   ?? [];
  const risks       = score.risks       ?? [];
  const missing     = score.missing_inputs ?? [];
  const summaryText = score.summary_explanation ?? "";
  const showLegacyReasoning = score.reasoning && !summaryText;

  const scoreColor =
    score.score >= 70 ? "text-seed-400"
    : score.score >= 50 ? "text-yellow-400"
    : "text-red-400";

  return (
    <div className="rounded-2xl border border-[#1e2d22] bg-[#111a14] overflow-hidden">

      {/* ── Header: decision + score + confidence badge ── */}
      <div
        className={`p-6 flex items-start justify-between gap-4 ${
          isBid
            ? "bg-seed-900/40 border-b border-seed-800/50"
            : "bg-red-950/30 border-b border-red-900/30"
        }`}
      >
        <div className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-widest text-[#6b8f72]">
            Bid Recommendation
          </p>
          <div className={`text-2xl font-bold ${isBid ? "text-seed-400" : "text-red-400"}`}>
            {isBid ? "✓ BID" : "✗ NO BID"}
          </div>
          {confidence !== "high" && <ConfidenceBadge confidence={confidence} />}
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-1">Score</p>
          <div className={`text-4xl font-bold font-mono ${scoreColor}`}>{score.score}</div>
        </div>
      </div>

      {/* ── Summary explanation ── */}
      {summaryText && (
        <div className="px-6 pt-6">
          <div className="rounded-xl bg-[#0a0f0d] border border-[#1e2d22] p-4">
            <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-2">
              Recommendation Rationale
            </p>
            <p className="text-sm text-[#d1fae5] leading-relaxed">{summaryText}</p>
          </div>
        </div>
      )}

      {/* ── Factor breakdown ── */}
      <div className="p-6 space-y-5">
        <p className="text-xs uppercase tracking-widest text-[#6b8f72]">
          Score Breakdown
        </p>
        {FACTORS.map(({ key, label, weight }) => {
          const detail = score.factor_details?.[key];
          const rawScore = score.breakdown[key] ?? 50;
          const evidenceText = detail?.evidence &&
            detail.evidence !== "Not stated" &&
            detail.evidence !== "Not specified" &&
            detail.evidence !== "N/A"
              ? detail.evidence
              : null;

          return (
            <div key={key}>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-[#e8f5eb]">{label}</span>
                <span className="text-[#6b8f72]">{weight}</span>
              </div>
              <ScoreBar value={rawScore} />
              {detail?.explanation && (
                <p className="text-xs text-[#6b8f72] mt-1.5 leading-relaxed">
                  {detail.explanation}
                  {evidenceText && (
                    <span className="italic text-[#4a6b52]"> — &ldquo;{evidenceText}&rdquo;</span>
                  )}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Strengths ── */}
      {strengths.length > 0 && (
        <div className="px-6 pb-5">
          <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-3">Strengths</p>
          <ul className="space-y-2">
            {strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[#d1fae5]">
                <span className="text-seed-400 mt-0.5 shrink-0">✓</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Risks ── */}
      {risks.length > 0 && (
        <div className="px-6 pb-5">
          <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-3">Scoring Risks</p>
          <ul className="space-y-2">
            {risks.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-yellow-300/90">
                <span className="text-yellow-500 mt-0.5 shrink-0">⚠</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Missing inputs notice ── */}
      {missing.length > 0 && (
        <div className="px-6 pb-5">
          <div className="rounded-xl bg-[#0a0f0d] border border-[#1e2d22] p-4">
            <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-2">
              What would sharpen this score
            </p>
            <ul className="space-y-1">
              {missing.map((m, i) => (
                <li key={i} className="text-xs text-[#6b8f72] leading-relaxed">
                  · {m}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* ── Legacy reasoning (only shown for pre-1.3 records without summary) ── */}
      {showLegacyReasoning && (
        <div className="px-6 pb-6">
          <div className="rounded-xl bg-[#0a0f0d] border border-[#1e2d22] p-4">
            <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-2">Reasoning</p>
            <p className="text-sm text-[#d1fae5] leading-relaxed">{score.reasoning}</p>
          </div>
        </div>
      )}
    </div>
  );
}
