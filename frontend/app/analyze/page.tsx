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
  { id: "",                       label: "General (neutral)"       },
  { id: "technology",             label: "Technology"              },
  { id: "consulting",             label: "Consulting"              },
  { id: "healthcare",             label: "Healthcare"              },
  { id: "construction",           label: "Construction"            },
  { id: "government_contracting", label: "Government Contracting"  },
  { id: "education",              label: "Education"               },
];

export default function AnalyzePage() {
  const [loading, setLoading]               = useState(false);
  const [error, setError]                   = useState<string | null>(null);
  const [industry, setIndustry]             = useState<string>("");
  const [samResults, setSamResults]         = useState<SAMOpportunity[] | null>(null);
  const [samTotal, setSamTotal]             = useState(0);
  const [analyzingId, setAnalyzingId]       = useState<string | null>(null);
  const router = useRouter();

  const handleResult = (data: { id: string }) => router.push(`/analysis/${data.id}`);

  const handleAnalyzePDF = async (file: File) => {
    setLoading(true); setError(null); setSamResults(null);
    const fd = new FormData();
    fd.append("file", file);
    if (industry) fd.append("industry", industry);
    try {
      const r = await fetch("/api/analyze", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || "Analysis failed");
      handleResult(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setLoading(false);
    }
  };

  const handleAnalyzeURL = async (url: string) => {
    setLoading(true); setError(null); setSamResults(null);
    try {
      const r = await fetch("/api/analyze-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, industry: industry || null }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || "Analysis failed");
      handleResult(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setLoading(false);
    }
  };

  const handleSAMSearch = async (query: string, naics: string) => {
    setLoading(true); setError(null); setSamResults(null);
    try {
      const params = new URLSearchParams({ q: query, limit: "10" });
      if (naics) params.set("naics", naics);
      const r = await fetch(`/api/sam/search?${params}`);
      if (!r.ok) throw new Error((await r.json()).detail || "Search failed");
      const data = await r.json();
      setSamResults(data.opportunities);
      setSamTotal(data.totalRecords);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally { setLoading(false); }
  };

  const handleSAMAnalyze = async (noticeId: string) => {
    setAnalyzingId(noticeId); setError(null);
    try {
      const r = await fetch(`/api/sam/analyze/${noticeId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ industry: industry || null }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || "Analysis failed");
      handleResult(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setAnalyzingId(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-14">
      {/* Header */}
      <div className="text-center mb-12">
        <h1 className="text-3xl font-bold text-[#fafafa] tracking-tight mb-3">
          Analyze an RFP
        </h1>
        <p className="text-[#71717a] max-w-md mx-auto text-sm leading-relaxed">
          Upload a PDF, paste a URL, or search SAM.gov federal opportunities.
          Results are ready in under a minute.
        </p>
      </div>

      {/* Industry */}
      <div className="max-w-xl mx-auto mb-5">
        <label className="block text-xs text-[#71717a] mb-1.5 font-medium">Industry</label>
        <select
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="w-full bg-[#111113] border border-[#27272a] rounded-xl px-4 py-2.5 text-sm text-[#fafafa] focus:outline-none focus:border-seed-700 transition-colors appearance-none cursor-pointer"
        >
          {INDUSTRIES.map((ind) => (
            <option key={ind.id} value={ind.id} className="bg-[#111113]">{ind.label}</option>
          ))}
        </select>
        <p className="mt-1.5 text-xs text-[#52525b]">
          Scoring and proposals adapt to the selected industry context.
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
            analyzing={analyzingId}
          />
        </div>
      )}
    </div>
  );
}
