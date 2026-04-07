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

function WeightSlider({
  id,
  label,
  hint,
  value,
  onChange,
}: {
  id: keyof Weights;
  label: string;
  hint: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium text-[#e8f5eb]">{label}</span>
          <p className="text-xs text-[#6b8f72] mt-0.5">{hint}</p>
        </div>
        <span className="text-sm font-mono font-bold text-seed-400 w-12 text-right">
          {Math.round(value * 100)}%
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={5}
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
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/scoring-config")
      .then((r) => r.json())
      .then((data) => setConfig(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalWeight = Object.values(config.weights).reduce((s, v) => s + v, 0);
  const weightError = Math.abs(totalWeight - 1) > 0.01;

  const setWeight = (key: keyof Weights, value: number) =>
    setConfig((c) => ({ ...c, weights: { ...c.weights, [key]: value } }));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (weightError) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch("/api/scoring-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.detail || "Failed to save");
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-[#6b8f72] text-sm">
        Loading settings…
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#e8f5eb]">Settings</h1>
        <p className="text-sm text-[#6b8f72] mt-1">Configure scoring weights and bid threshold.</p>
      </div>

      <form onSubmit={handleSave} className="space-y-8">
        {/* Score weights */}
        <div className="p-6 rounded-2xl border border-[#1e2d22] bg-[#0d1610]">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-sm font-semibold text-[#e8f5eb]">Score weights</h2>
            <span
              className={`text-xs font-mono px-2 py-0.5 rounded-full ${
                weightError
                  ? "text-red-400 bg-red-950/40 border border-red-900"
                  : "text-seed-400 bg-seed-900/40 border border-seed-800"
              }`}
            >
              Total: {Math.round(totalWeight * 100)}%
              {weightError ? " ✗ must equal 100%" : " ✓"}
            </span>
          </div>

          <div className="space-y-6">
            {(Object.keys(WEIGHT_LABELS) as (keyof Weights)[]).map((key) => (
              <WeightSlider
                key={key}
                id={key}
                label={WEIGHT_LABELS[key]}
                hint={WEIGHT_HINTS[key]}
                value={config.weights[key]}
                onChange={(v) => setWeight(key, v)}
              />
            ))}
          </div>
        </div>

        {/* Bid threshold */}
        <div className="p-6 rounded-2xl border border-[#1e2d22] bg-[#0d1610]">
          <h2 className="text-sm font-semibold text-[#e8f5eb] mb-1">Bid threshold</h2>
          <p className="text-xs text-[#6b8f72] mb-4">
            Analyses scoring at or above this value get a BID recommendation.
          </p>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-[#6b8f72]">Minimum score to BID</span>
            <span className="text-sm font-mono font-bold text-seed-400">
              {config.bid_threshold}
            </span>
          </div>
          <input
            type="range"
            min={30}
            max={90}
            step={5}
            value={config.bid_threshold}
            onChange={(e) =>
              setConfig((c) => ({ ...c, bid_threshold: Number(e.target.value) }))
            }
            className="w-full accent-seed-500 cursor-pointer"
          />
          <div className="flex justify-between text-xs text-[#3d5c44] mt-1">
            <span>30 (permissive)</span>
            <span>90 (strict)</span>
          </div>
        </div>

        {/* Strategic fit weight */}
        <div className="p-6 rounded-2xl border border-[#1e2d22] bg-[#0d1610]">
          <h2 className="text-sm font-semibold text-[#e8f5eb] mb-1">Strategic fit weight</h2>
          <p className="text-xs text-[#6b8f72] mb-4">
            Influence of company profile alignment on the final score (requires profile to be configured).
          </p>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-[#6b8f72]">Weight</span>
            <span className="text-sm font-mono font-bold text-seed-400">
              {Math.round(config.strategic_fit_weight * 100)}%
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={40}
            step={5}
            value={Math.round(config.strategic_fit_weight * 100)}
            onChange={(e) =>
              setConfig((c) => ({
                ...c,
                strategic_fit_weight: Number(e.target.value) / 100,
              }))
            }
            className="w-full accent-seed-500 cursor-pointer"
          />
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={saving || weightError}
          className="w-full py-3 rounded-xl bg-seed-600 hover:bg-seed-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
