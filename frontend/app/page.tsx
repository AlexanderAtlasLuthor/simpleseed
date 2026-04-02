"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadZone from "./components/UploadZone";

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleAnalyze = async (file: File) => {
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Analysis failed");
      }

      const data = await res.json();
      router.push(`/analysis/${data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-20">
      {/* Hero */}
      <div className="text-center mb-16">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-seed-800/60 bg-seed-900/20 text-seed-400 text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-seed-500 animate-pulse" />
          Powered by Claude AI
        </div>
        <h1 className="text-5xl font-bold text-[#e8f5eb] tracking-tight mb-4">
          Win more RFPs.
          <br />
          <span className="text-seed-400">Faster.</span>
        </h1>
        <p className="text-lg text-[#6b8f72] max-w-xl mx-auto leading-relaxed">
          Upload any RFP and get instant AI analysis: structured requirements,
          bid/no-bid scoring, and a ready-to-customize proposal draft.
        </p>
      </div>

      {/* Upload */}
      <UploadZone onAnalyze={handleAnalyze} loading={loading} />

      {error && (
        <div className="mt-4 max-w-xl mx-auto p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* How it works */}
      <div className="mt-24 grid grid-cols-1 md:grid-cols-4 gap-6 max-w-4xl mx-auto">
        {[
          { step: "01", icon: "📄", title: "Upload RFP", desc: "Drop your PDF file" },
          { step: "02", icon: "🔍", title: "Extract", desc: "AI pulls requirements, deadlines, budget" },
          { step: "03", icon: "📊", title: "Score", desc: "Bid/no-bid decision with reasoning" },
          { step: "04", icon: "✍️", title: "Propose", desc: "Draft proposal ready to customize" },
        ].map(({ step, icon, title, desc }) => (
          <div key={step} className="text-center">
            <div className="text-3xl mb-3">{icon}</div>
            <div className="text-xs font-mono text-seed-600 mb-1">{step}</div>
            <div className="font-semibold text-[#e8f5eb] text-sm mb-1">{title}</div>
            <div className="text-xs text-[#6b8f72]">{desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
