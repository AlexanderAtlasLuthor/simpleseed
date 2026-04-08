"use client";
import { useEffect, useState } from "react";

interface Weights {
  relevance_score: number;
  budget_fit: number;
  requirements_match: number;
  completeness: number;
}
interface ScoringConfig {
  weights: Weights;
  bid_threshold: number;
  strategic_fit_weight: number;
}

const WEIGHT_LABELS: Record<keyof Weights, string> = {
  relevance_score:    "Relevance",
  budget_fit:         "Budget fit",
  requirements_match: "Requirements match",
  completeness:       "Completeness",
};
const WEIGHT_HINTS: Record<keyof Weights, string> = {
  relevance_score:    "How well the RFP aligns with your core expertise",
  budget_fit:         "Whether budget is realistic and explicitly stated",
  requirements_match: "How achievable the mandatory requirements are",
  completeness:       "Clarity of timeline, deliverables, and evaluation criteria",
};

function WeightSlider({ label, hint, value, onChange }: {
  label: string; hint: string; value: number; onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="text-sm font-medium text-[#fafafa]">{label}</span>
          <p className="text-xs text-[#71717a] mt-0.5">{hint}</p>
        </div>
        <span className="text-sm font-mono font-bold text-seed-400 shrink-0 w-10 text-right">
          {Math.round(value * 100)}%
        </span>
      </div>
      <input
        type="range" min={0} max={100} step={5}
        value={Math.round(value * 100)}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        className="w-full accent-seed-500 cursor-pointer"
      />
    </div>
  );
}

export default function SettingsPage() {
  const [config, setConfig] = useState<ScoringConfig>({
    weights: { relevance_score: 0.3, budget_fit: 0.25, requirements_match: 0.25, completeness: 0.2 },
    bid_threshold: 60,
    strategic_fit_weight: 0.2,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/scoring-config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalWeight  = Object.values(config.weights).reduce((s, v) => s + v, 0);
  const weightError  = Math.abs(totalWeight - 1) > 0.01;
  const setWeight    = (key: keyof Weights, v: number) =>
    setConfig((c) => ({ ...c, weights: { ...c.weights, [key]: v } }));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (weightError) return;
    setSaving(true); setError(null); setSaved(false);
    try {
      const res = await fetch("/api/scoring-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Failed to save");
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-[#71717a] text-sm">Loading settings…</div>;
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#fafafa]">Settings</h1>
        <p className="text-sm text-[#71717a] mt-1">Configure scoring weights and bid threshold.</p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">

        {/* Weights */}
        <div className="p-6 rounded-xl border border-[#27272a] bg-[#111113]">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-sm font-semibold text-[#fafafa]">Score weights</h2>
            <span className={`text-xs font-mono px-2 py-0.5 rounded-full border ${
              weightError
                ? "text-red-400 bg-red-950/40 border-red-900"
                : "text-seed-400 bg-seed-950/40 border-seed-900"
            }`}>
              {Math.round(totalWeight * 100)}% {weightError ? "— must equal 100%" : "total"}
            </span>
          </div>
          <div className="space-y-6">
            {(Object.keys(WEIGHT_LABELS) as (keyof Weights)[]).map((key) => (
              <WeightSlider
                key={key}
                label={WEIGHT_LABELS[key]}
                hint={WEIGHT_HINTS[key]}
                value={config.weights[key]}
                onChange={(v) => setWeight(key, v)}
              />
            ))}
          </div>
        </div>

        {/* Bid threshold */}
        <div className="p-6 rounded-xl border border-[#27272a] bg-[#111113]">
          <h2 className="text-sm font-semibold text-[#fafafa] mb-1">Bid threshold</h2>
          <p className="text-xs text-[#71717a] mb-4">
            Analyses scoring at or above this value receive a BID recommendation.
          </p>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-[#71717a]">Minimum score to BID</span>
            <span className="text-sm font-mono font-bold text-seed-400">{config.bid_threshold}</span>
          </div>
          <input
            type="range" min={30} max={90} step={5}
            value={config.bid_threshold}
            onChange={(e) => setConfig((c) => ({ ...c, bid_threshold: Number(e.target.value) }))}
            className="w-full accent-seed-500 cursor-pointer"
          />
          <div className="flex justify-between text-xs text-[#52525b] mt-1">
            <span>30 — permissive</span>
            <span>90 — strict</span>
          </div>
        </div>

        {/* Strategic fit */}
        <div className="p-6 rounded-xl border border-[#27272a] bg-[#111113]">
          <h2 className="text-sm font-semibold text-[#fafafa] mb-1">Strategic fit weight</h2>
          <p className="text-xs text-[#71717a] mb-4">
            Influence of company profile alignment on the final score.
            Requires profile to be configured.
          </p>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-[#71717a]">Weight</span>
            <span className="text-sm font-mono font-bold text-seed-400">
              {Math.round(config.strategic_fit_weight * 100)}%
            </span>
          </div>
          <input
            type="range" min={0} max={40} step={5}
            value={Math.round(config.strategic_fit_weight * 100)}
            onChange={(e) => setConfig((c) => ({ ...c, strategic_fit_weight: Number(e.target.value) / 100 }))}
            className="w-full accent-seed-500 cursor-pointer"
          />
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">{error}</div>
        )}

        <button
          type="submit"
          disabled={saving || weightError}
          className="w-full py-2.5 rounded-xl bg-seed-600 hover:bg-seed-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
        >
          {saving ? "Saving…" : saved ? "Saved" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
