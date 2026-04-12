"use client";
import { useState } from "react";

interface FeedbackState {
  was_correct: boolean | null;
  outcome: "won" | "lost" | "not_pursued" | null;
  comment: string;
}

interface Props {
  rfpId: string;
}

export default function FeedbackPanel({ rfpId }: Props) {
  const [feedback, setFeedback] = useState<FeedbackState>({
    was_correct: null,
    outcome: null,
    comment: "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(patch: Partial<FeedbackState>) {
    const next = { ...feedback, ...patch };
    setFeedback(next);
    setSaving(true);
    setError(null);
    setSaved(false);

    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rfp_id: rfpId,
          was_correct: next.was_correct,
          outcome: next.outcome,
          comment: next.comment || null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to save feedback");
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  }

  const btnBase =
    "flex-1 py-2 px-3 rounded-lg border text-sm font-medium transition-all";
  const btnActive = "bg-seed-900/60 border-seed-700 text-seed-300";
  const btnInactive = "border-[#1e2d22] text-[#6b8f72] hover:text-[#e8f5eb] hover:border-[#2d4a35]";

  return (
    <div className="mt-8 rounded-xl border border-[#1e2d22] bg-[#0d1610] p-5">
      <h3 className="text-sm font-semibold text-[#e8f5eb] mb-4">
        Feedback &amp; Outcome
      </h3>

      {/* Was this recommendation correct? */}
      <div className="mb-5">
        <p className="text-xs text-[#6b8f72] mb-2 uppercase tracking-wide">
          Was this recommendation correct?
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => submit({ was_correct: true })}
            className={`${btnBase} ${
              feedback.was_correct === true ? btnActive : btnInactive
            }`}
          >
            👍 Yes
          </button>
          <button
            onClick={() => submit({ was_correct: false })}
            className={`${btnBase} ${
              feedback.was_correct === false ? "bg-red-950/60 border-red-800 text-red-400" : btnInactive
            }`}
          >
            👎 No
          </button>
        </div>
      </div>

      {/* Outcome */}
      <div className="mb-5">
        <p className="text-xs text-[#6b8f72] mb-2 uppercase tracking-wide">
          Outcome
        </p>
        <div className="flex gap-2">
          {(
            [
              { value: "won", label: "Won" },
              { value: "lost", label: "Lost" },
              { value: "not_pursued", label: "Not pursued" },
            ] as const
          ).map(({ value, label }) => (
            <button
              key={value}
              onClick={() => submit({ outcome: value })}
              className={`${btnBase} ${
                feedback.outcome === value ? btnActive : btnInactive
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Comment */}
      <div className="mb-4">
        <p className="text-xs text-[#6b8f72] mb-2 uppercase tracking-wide">
          Comment (optional)
        </p>
        <textarea
          value={feedback.comment}
          onChange={(e) => setFeedback((f) => ({ ...f, comment: e.target.value }))}
          onBlur={() => feedback.comment && submit({})}
          placeholder="Any context about this result..."
          rows={2}
          className="w-full rounded-lg bg-[#111a14] border border-[#1e2d22] text-sm text-[#e8f5eb] placeholder-[#3d5c45] px-3 py-2 focus:outline-none focus:border-seed-700 resize-none"
        />
      </div>

      {/* Status indicators */}
      <div className="h-4 flex items-center">
        {saving && (
          <span className="text-xs text-[#6b8f72] flex items-center gap-1">
            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Saving...
          </span>
        )}
        {saved && !saving && (
          <span className="text-xs text-seed-400">Saved</span>
        )}
        {error && !saving && (
          <span className="text-xs text-red-400">{error}</span>
        )}
      </div>
    </div>
  );
}
