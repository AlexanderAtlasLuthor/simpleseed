"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadZone from "../components/UploadZone";
import SAMResults from "../components/SAMResults";

interface SAMOpportunity {
  noticeId: string;
  title: string;
  agency: string;
  type: string;
  naicsCode: string;
  postedDate: string;
  responseDeadLine: string;
  setAside: string;
  uiLink: string;
}

const INDUSTRIES = [
  { id: "",                       label: "General (neutral)"        },
  { id: "technology",             label: "Technology"               },
  { id: "consulting",             label: "Consulting"               },
  { id: "healthcare",             label: "Healthcare"               },
  { id: "construction",           label: "Construction"             },
  { id: "government_contracting", label: "Government Contracting"   },
  { id: "education",              label: "Education"                },
];

export default function AnalyzePage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [industry, setIndustry] = useState<string>("");
  const [samResults, setSamResults] = useState<SAMOpportunity[] | null>(null);
  const [samTotal, setSamTotal] = useState(0);
  const [analyzingNoticeId, setAnalyzingNoticeId] = useState<string | null>(null);

  const router = useRouter();
  const handleResult = (data: { id: string }) => router.push(`/analysis/${data.id}`);

  const handleAnalyzePDF = async (file: File) => {
    setLoading(true);
    setError(null);
    setSamResults(null);
    const formData = new FormData();
    formData.append("file", file);
    if (industry) formData.append("industry", industry);
    try {
      const res = await fetch("/api/analyze", { method: "POST", body: formData });
      if (!res.ok) throw new Error((await res.json()).detail || "Analysis failed");
      handleResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setLoading(false);
    }
  };

  const handleAnalyzeURL = async (url: string) => {
    setLoading(true);
    setError(null);
    setSamResults(null);
    try {
      const res = await fetch("/api/analyze-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, industry: industry || null }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Analysis failed");
      handleResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setLoading(false);
    }
  };

  const handleSAMSearch = async (query: string, naics: string) => {
    setLoading(true);
    setError(null);
    setSamResults(null);
    try {
      const params = new URLSearchParams({ q: query, limit: "10" });
      if (naics) params.set("naics", naics);
      const res = await fetch(`/api/sam/search?${params}`);
      if (!res.ok) throw new Error((await res.json()).detail || "Search failed");
      const data = await res.json();
      setSamResults(data.opportunities);
      setSamTotal(data.totalRecords);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleSAMAnalyze = async (noticeId: string) => {
    setAnalyzingNoticeId(noticeId);
    setError(null);
    try {
      const res = await fetch(`/api/sam/analyze/${noticeId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ industry: industry || null }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Analysis failed");
      handleResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setAnalyzingNoticeId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-16">
      {/* Header */}
      <div className="text-center mb-14">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-seed-800/60 bg-seed-900/20 text-seed-400 text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-seed-500 animate-pulse" />
          Powered by Claude AI
        </div>
        <h1 className="text-5xl font-bold text-[#e8f5eb] tracking-tight mb-4">
          Analyze an RFP
        </h1>
        <p className="text-lg text-[#6b8f72] max-w-xl mx-auto leading-relaxed">
          Upload a PDF, paste a link, or search SAM.gov — get instant AI analysis,
          bid scoring, and a ready-to-customize proposal.
        </p>
      </div>

      {/* Industry selector */}
      <div className="max-w-xl mx-auto mb-4">
        <label className="block text-xs text-[#6b8f72] mb-2">Your industry</label>
        <select
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="w-full bg-[#0a0f0d] border border-[#1e2d22] rounded-xl px-4 py-2.5 text-sm text-[#e8f5eb] focus:outline-none focus:border-seed-700 transition-colors appearance-none cursor-pointer"
        >
          {INDUSTRIES.map((ind) => (
            <option key={ind.id} value={ind.id} className="bg-[#0a0f0d]">
              {ind.label}
            </option>
          ))}
        </select>
        <p className="mt-1.5 text-xs text-[#3d5c44]">
          Proposals and scoring adapt to the selected industry context.
        </p>
      </div>

      <UploadZone
        onAnalyzePDF={handleAnalyzePDF}
        onAnalyzeURL={handleAnalyzeURL}
        onSAMSearch={handleSAMSearch}
        loading={loading}
      />

      {error && (
        <div className="mt-4 max-w-xl mx-auto p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">
          {error}
        </div>
      )}

      {samResults !== null && (
        <div className="mt-10 max-w-2xl mx-auto">
          <SAMResults
            opportunities={samResults}
            total={samTotal}
            onAnalyze={handleSAMAnalyze}
            analyzing={analyzingNoticeId}
          />
        </div>
      )}

      {samResults === null && (
        <div className="mt-24 grid grid-cols-1 md:grid-cols-4 gap-6 max-w-4xl mx-auto">
          {[
            { step: "01", icon: "📄", title: "Upload RFP",  desc: "PDF, URL, or SAM.gov search" },
            { step: "02", icon: "🔍", title: "Extract",     desc: "AI pulls requirements, deadlines, budget" },
            { step: "03", icon: "📊", title: "Score",       desc: "Bid/no-bid decision with reasoning" },
            { step: "04", icon: "✍️", title: "Propose",     desc: "Draft proposal ready to customize" },
          ].map(({ step, icon, title, desc }) => (
            <div key={step} className="text-center">
              <div className="text-3xl mb-3">{icon}</div>
              <div className="text-xs font-mono text-seed-600 mb-1">{step}</div>
              <div className="font-semibold text-[#e8f5eb] text-sm mb-1">{title}</div>
              <div className="text-xs text-[#6b8f72]">{desc}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
