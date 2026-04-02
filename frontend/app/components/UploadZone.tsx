"use client";
import { useRef, useState } from "react";

type InputMode = "pdf" | "url" | "sam";

interface Props {
  onAnalyzePDF: (file: File) => void;
  onAnalyzeURL: (url: string) => void;
  onSAMSearch: (query: string, naics: string) => void;
  loading: boolean;
}

// ─── PDF Tab ────────────────────────────────────────────────────────────────

function PDFTab({ onAnalyze, loading }: { onAnalyze: (f: File) => void; loading: boolean }) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf")) { alert("Please select a PDF file."); return; }
    setFile(f);
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
        onClick={() => !file && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-200 ${
          dragging ? "border-seed-500 bg-seed-500/10"
          : file ? "border-seed-600 bg-seed-900/20 cursor-default"
          : "border-[#1e2d22] hover:border-seed-700 hover:bg-[#111a14]"
        }`}
      >
        <input ref={inputRef} type="file" accept=".pdf" className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
        {file ? (
          <div className="space-y-2">
            <div className="text-4xl">📄</div>
            <p className="font-medium text-[#e8f5eb]">{file.name}</p>
            <p className="text-xs text-[#6b8f72]">{(file.size / 1024).toFixed(1)} KB</p>
            <button onClick={(e) => { e.stopPropagation(); setFile(null); }}
              className="text-xs text-[#6b8f72] hover:text-red-400 underline">Remove</button>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-4xl">📂</div>
            <p className="font-medium text-[#e8f5eb]">Drop your RFP here</p>
            <p className="text-sm text-[#6b8f72]">or click to browse — PDF only</p>
          </div>
        )}
      </div>
      <AnalyzeButton disabled={!file || loading} loading={loading} onClick={() => file && onAnalyze(file)} />
    </div>
  );
}

// ─── URL Tab ─────────────────────────────────────────────────────────────────

function URLTab({ onAnalyze, loading }: { onAnalyze: (url: string) => void; loading: boolean }) {
  const [url, setUrl] = useState("");

  const valid = url.startsWith("http://") || url.startsWith("https://");

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-[#6b8f72] mb-2">Paste a link to the RFP</label>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://portal.example.gov/rfp/2024-001.pdf"
          className="w-full bg-[#0a0f0d] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#6b8f72] focus:outline-none focus:border-seed-700 transition-colors"
        />
      </div>
      <div className="rounded-xl bg-[#0a0f0d] border border-[#1e2d22] p-4 space-y-1.5">
        <p className="text-xs font-medium text-[#6b8f72]">Works with:</p>
        {[
          "Direct PDF links (.pdf URL)",
          "Public HTML RFP pages",
          "SAM.gov public opportunity pages",
          "State procurement portal listings",
        ].map((t) => (
          <p key={t} className="text-xs text-[#6b8f72] flex gap-2">
            <span className="text-seed-600">✓</span>{t}
          </p>
        ))}
      </div>
      <AnalyzeButton disabled={!valid || loading} loading={loading} onClick={() => onAnalyze(url)} />
    </div>
  );
}

// ─── SAM.gov Tab ─────────────────────────────────────────────────────────────

function SAMTab({ onSearch, loading }: { onSearch: (q: string, naics: string) => void; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [naics, setNaics] = useState("");

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-[#6b8f72] mb-2">Keywords</label>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && query && onSearch(query, naics)}
          placeholder="e.g. cybersecurity, cloud migration, IT services"
          className="w-full bg-[#0a0f0d] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#6b8f72] focus:outline-none focus:border-seed-700 transition-colors"
        />
      </div>
      <div>
        <label className="block text-xs text-[#6b8f72] mb-2">
          NAICS Code <span className="text-[#1e2d22]">— optional</span>
        </label>
        <input
          type="text"
          value={naics}
          onChange={(e) => setNaics(e.target.value)}
          placeholder="e.g. 541512"
          className="w-full bg-[#0a0f0d] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#6b8f72] focus:outline-none focus:border-seed-700 transition-colors"
        />
      </div>
      <div className="rounded-xl bg-[#0a0f0d] border border-[#1e2d22] p-4">
        <p className="text-xs text-[#6b8f72]">
          Searches active U.S. federal contract opportunities on{" "}
          <span className="text-seed-500">SAM.gov</span>.{" "}
          Requires a free <code className="text-xs">SAM_GOV_API_KEY</code> in your backend <code>.env</code>.
        </p>
      </div>
      <AnalyzeButton
        disabled={!query || loading}
        loading={loading}
        label="Search SAM.gov"
        loadingLabel="Searching..."
        onClick={() => onSearch(query, naics)}
      />
    </div>
  );
}

// ─── Shared button ────────────────────────────────────────────────────────────

function AnalyzeButton({
  disabled,
  loading,
  onClick,
  label = "Analyze RFP",
  loadingLabel = "Analyzing RFP...",
}: {
  disabled: boolean;
  loading: boolean;
  onClick: () => void;
  label?: string;
  loadingLabel?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`mt-2 w-full py-3 rounded-xl font-semibold text-sm transition-all duration-200 ${
        !disabled
          ? "bg-seed-600 hover:bg-seed-500 text-white shadow-lg shadow-seed-900/50"
          : "bg-[#1e2d22] text-[#6b8f72] cursor-not-allowed"
      }`}
    >
      {loading ? (
        <span className="flex items-center justify-center gap-2">
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {loadingLabel}
        </span>
      ) : label}
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

const TABS: { id: InputMode; label: string; icon: string; badge?: string }[] = [
  { id: "pdf",  label: "Upload PDF", icon: "📄" },
  { id: "url",  label: "Paste URL",  icon: "🔗" },
  { id: "sam",  label: "SAM.gov",    icon: "🏛️", badge: "US Federal" },
];

export default function UploadZone({ onAnalyzePDF, onAnalyzeURL, onSAMSearch, loading }: Props) {
  const [mode, setMode] = useState<InputMode>("pdf");

  return (
    <div className="w-full max-w-xl mx-auto">
      {/* Tab switcher */}
      <div className="flex gap-1 p-1 rounded-xl bg-[#111a14] border border-[#1e2d22] mb-5">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setMode(tab.id)}
            className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 rounded-lg text-xs font-medium transition-all ${
              mode === tab.id
                ? "bg-seed-900/60 text-seed-400 border border-seed-800/50"
                : "text-[#6b8f72] hover:text-[#e8f5eb]"
            }`}
          >
            <span className="text-base">{tab.icon}</span>
            <span>{tab.label}</span>
            {tab.badge && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-seed-900/50 text-seed-600 border border-seed-800/40">
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Active tab content */}
      {mode === "pdf" && <PDFTab onAnalyze={onAnalyzePDF} loading={loading} />}
      {mode === "url" && <URLTab onAnalyze={onAnalyzeURL} loading={loading} />}
      {mode === "sam" && <SAMTab onSearch={onSAMSearch} loading={loading} />}
    </div>
  );
}
