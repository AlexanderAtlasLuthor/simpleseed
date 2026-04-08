"use client";
import { useRef, useState } from "react";
import { FileTextIcon, LinkIcon, BuildingIcon, FolderOpenIcon, SpinnerIcon } from "./Icons";

type InputMode = "pdf" | "url" | "sam";

interface Props {
  onAnalyzePDF: (file: File) => void;
  onAnalyzeURL: (url: string) => void;
  onSAMSearch:  (query: string, naics: string) => void;
  loading: boolean;
}

// ─── Shared button ────────────────────────────────────────────────────────────

function PrimaryButton({
  disabled, loading, onClick,
  label = "Analyze RFP", loadingLabel = "Analyzing…",
}: {
  disabled: boolean; loading: boolean; onClick: () => void;
  label?: string; loadingLabel?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`mt-3 w-full py-2.5 rounded-xl font-semibold text-sm transition-all ${
        !disabled
          ? "bg-seed-600 hover:bg-seed-500 text-white"
          : "bg-[#18181b] text-[#52525b] cursor-not-allowed border border-[#27272a]"
      }`}
    >
      {loading
        ? <span className="flex items-center justify-center gap-2">
            <SpinnerIcon className="h-4 w-4" />
            {loadingLabel}
          </span>
        : label}
    </button>
  );
}

// ─── PDF Tab ─────────────────────────────────────────────────────────────────

function PDFTab({ onAnalyze, loading }: { onAnalyze: (f: File) => void; loading: boolean }) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile]         = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf")) { alert("Please select a PDF file."); return; }
    setFile(f);
  };

  return (
    <div>
      <div
        onDragOver={(e)  => { e.preventDefault(); setDragging(true); }}
        onDragLeave={()  => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
        onClick={() => !file && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
          dragging ? "border-seed-500 bg-seed-950/30"
          : file   ? "border-seed-800 bg-seed-950/20 cursor-default"
          :          "border-[#27272a] hover:border-[#3f3f46] hover:bg-[#111113]"
        }`}
      >
        <input ref={inputRef} type="file" accept=".pdf" className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
        {file ? (
          <div className="space-y-2">
            <div className="flex justify-center">
              <FileTextIcon className="h-8 w-8 text-seed-400" />
            </div>
            <p className="font-medium text-[#fafafa] text-sm">{file.name}</p>
            <p className="text-xs text-[#71717a]">{(file.size / 1024).toFixed(1)} KB</p>
            <button onClick={(e) => { e.stopPropagation(); setFile(null); }}
              className="text-xs text-[#52525b] hover:text-red-400 underline transition-colors">
              Remove
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex justify-center">
              <FolderOpenIcon className="h-8 w-8 text-[#52525b]" />
            </div>
            <p className="font-medium text-[#fafafa] text-sm">Drop your RFP here</p>
            <p className="text-xs text-[#71717a]">or click to browse — PDF only</p>
          </div>
        )}
      </div>
      <PrimaryButton disabled={!file || loading} loading={loading} onClick={() => file && onAnalyze(file)} />
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
        <label className="block text-xs text-[#71717a] mb-1.5 font-medium">URL to RFP</label>
        <input
          type="url" value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="https://portal.example.gov/rfp/2024-001.pdf"
          className="w-full bg-[#111113] border border-[#27272a] rounded-xl px-4 py-2.5 text-sm text-[#fafafa] placeholder-[#52525b] focus:outline-none focus:border-seed-700 transition-colors"
        />
      </div>
      <div className="rounded-xl bg-[#111113] border border-[#27272a] p-4 space-y-1.5">
        <p className="text-xs font-medium text-[#52525b] mb-2">Supported sources</p>
        {["Direct PDF links (.pdf URL)", "Public HTML RFP pages", "SAM.gov public opportunity pages", "State procurement portals"].map((t) => (
          <p key={t} className="text-xs text-[#71717a] flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-seed-600 shrink-0" />
            {t}
          </p>
        ))}
      </div>
      <PrimaryButton disabled={!valid || loading} loading={loading} onClick={() => onAnalyze(url)} />
    </div>
  );
}

// ─── SAM Tab ─────────────────────────────────────────────────────────────────

function SAMTab({ onSearch, loading }: { onSearch: (q: string, naics: string) => void; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [naics, setNaics] = useState("");

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-[#71717a] mb-1.5 font-medium">Keywords</label>
        <input
          type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && query && onSearch(query, naics)}
          placeholder="e.g. cybersecurity, cloud migration, IT services"
          className="w-full bg-[#111113] border border-[#27272a] rounded-xl px-4 py-2.5 text-sm text-[#fafafa] placeholder-[#52525b] focus:outline-none focus:border-seed-700 transition-colors"
        />
      </div>
      <div>
        <label className="block text-xs text-[#71717a] mb-1.5 font-medium">
          NAICS Code <span className="text-[#3f3f46] font-normal">— optional</span>
        </label>
        <input
          type="text" value={naics} onChange={(e) => setNaics(e.target.value)}
          placeholder="541512"
          className="w-full bg-[#111113] border border-[#27272a] rounded-xl px-4 py-2.5 text-sm text-[#fafafa] placeholder-[#52525b] focus:outline-none focus:border-seed-700 transition-colors"
        />
      </div>
      <p className="text-xs text-[#52525b]">
        Searches active U.S. federal contract opportunities on SAM.gov.
        Requires <code className="text-xs text-[#71717a]">SAM_GOV_API_KEY</code> in backend .env.
      </p>
      <PrimaryButton disabled={!query || loading} loading={loading} label="Search SAM.gov" loadingLabel="Searching…" onClick={() => onSearch(query, naics)} />
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

const TABS: { id: InputMode; label: string; Icon: typeof FileTextIcon; badge?: string }[] = [
  { id: "pdf",  label: "Upload PDF", Icon: FileTextIcon  },
  { id: "url",  label: "Paste URL",  Icon: LinkIcon      },
  { id: "sam",  label: "SAM.gov",    Icon: BuildingIcon, badge: "US Federal" },
];

export default function UploadZone({ onAnalyzePDF, onAnalyzeURL, onSAMSearch, loading }: Props) {
  const [mode, setMode] = useState<InputMode>("pdf");

  return (
    <div className="w-full max-w-xl mx-auto">
      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[#111113] border border-[#1c1c1f] mb-5">
        {TABS.map(({ id, label, Icon, badge }) => (
          <button
            key={id}
            onClick={() => setMode(id)}
            className={`flex-1 flex flex-col items-center gap-1 py-2.5 rounded-lg text-xs font-medium transition-all ${
              mode === id
                ? "bg-[#18181b] text-[#fafafa] border border-[#27272a]"
                : "text-[#71717a] hover:text-[#fafafa]"
            }`}
          >
            <Icon className="h-4 w-4" />
            <span>{label}</span>
            {badge && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-seed-950/60 text-seed-500 border border-seed-900/50">
                {badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {mode === "pdf" && <PDFTab onAnalyze={onAnalyzePDF} loading={loading} />}
      {mode === "url" && <URLTab onAnalyze={onAnalyzeURL} loading={loading} />}
      {mode === "sam" && <SAMTab onSearch={onSAMSearch}   loading={loading} />}
    </div>
  );
}
