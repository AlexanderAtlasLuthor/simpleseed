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
}

interface Props {
  score: ScoreData;
}

const factors = [
  { key: "relevance_score", label: "Relevance", weight: "30%" },
  { key: "budget_fit", label: "Budget Fit", weight: "25%" },
  { key: "requirements_match", label: "Requirements Match", weight: "25%" },
  { key: "completeness", label: "Completeness", weight: "20%" },
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

export default function ScoreCard({ score }: Props) {
  const isBid = score.decision === "BID";
  const scoreColor =
    score.score >= 70
      ? "text-seed-400"
      : score.score >= 50
      ? "text-yellow-400"
      : "text-red-400";

  return (
    <div className="rounded-2xl border border-[#1e2d22] bg-[#111a14] overflow-hidden">
      {/* Header */}
      <div
        className={`p-6 flex items-center justify-between ${
          isBid
            ? "bg-seed-900/40 border-b border-seed-800/50"
            : "bg-red-950/30 border-b border-red-900/30"
        }`}
      >
        <div>
          <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-1">
            Bid Recommendation
          </p>
          <div
            className={`text-2xl font-bold ${
              isBid ? "text-seed-400" : "text-red-400"
            }`}
          >
            {isBid ? "✓ BID" : "✗ NO BID"}
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-1">Score</p>
          <div className={`text-4xl font-bold font-mono ${scoreColor}`}>
            {score.score}
          </div>
        </div>
      </div>

      {/* Breakdown */}
      <div className="p-6 space-y-3">
        <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-4">
          Score Breakdown
        </p>
        {factors.map(({ key, label, weight }) => (
          <div key={key}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-[#e8f5eb]">{label}</span>
              <span className="text-[#6b8f72]">{weight}</span>
            </div>
            <ScoreBar value={score.breakdown[key] ?? 50} />
          </div>
        ))}
      </div>

      {/* Reasoning */}
      {score.reasoning && (
        <div className="px-6 pb-6">
          <div className="rounded-xl bg-[#0a0f0d] border border-[#1e2d22] p-4">
            <p className="text-xs uppercase tracking-widest text-[#6b8f72] mb-2">
              Reasoning
            </p>
            <p className="text-sm text-[#d1fae5] leading-relaxed">{score.reasoning}</p>
          </div>
        </div>
      )}
    </div>
  );
}
