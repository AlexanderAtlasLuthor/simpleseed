"use client";
import { useEffect, useRef, useState } from "react";
import { UploadIcon, DatabaseIcon, SpinnerIcon } from "../components/Icons";

interface KnowledgeDoc {
  document_id: string;
  filename: string;
  content_type: string;
  processing_status: "pending" | "completed" | "error";
  text_length: number | null;
  error_message: string | null;
  uploaded_at: string | null;
}

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-seed-950/40 border-seed-900/50 text-seed-400",
  pending:   "bg-yellow-950/40 border-yellow-900/50 text-yellow-500",
  error:     "bg-red-950/40 border-red-900/50 text-red-400",
};

export default function KnowledgePage() {
  const [docs, setDocs]           = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading]     = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [success, setSuccess]     = useState<string | null>(null);
  const [dragging, setDragging]   = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchDocs = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/knowledge");
      if (res.ok) setDocs(await res.json());
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchDocs(); }, []);

  const handleUpload = async (file: File) => {
    setError(null); setSuccess(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "txt"].includes(ext ?? "")) {
      setError("Only PDF and TXT files are supported."); return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res  = await fetch("/api/knowledge", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "Upload failed.");
      } else if (data.processing_status === "error") {
        setError(`File uploaded but text extraction failed: ${data.error_message}`);
      } else {
        setSuccess(`"${data.filename}" uploaded and indexed successfully.`);
        await fetchDocs();
      }
    } catch {
      setError("Network error — could not reach the backend.");
    } finally { setUploading(false); }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const formatBytes = (n: number | null) =>
    n === null ? "—" : n < 1000 ? `${n} chars` : `${(n / 1000).toFixed(1)}k chars`;

  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#fafafa] tracking-tight mb-1">Knowledge Base</h1>
        <p className="text-sm text-[#71717a]">
          Upload past proposals or reference documents. Used to ground proposal generation
          and improve strategic context.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center transition-all mb-4 ${
          dragging  ? "border-seed-500 bg-seed-950/30 cursor-copy"
          : uploading ? "border-[#27272a] bg-[#111113] cursor-wait"
          :             "border-[#27272a] hover:border-[#3f3f46] hover:bg-[#111113] cursor-pointer"
        }`}
      >
        <input ref={inputRef} type="file" accept=".pdf,.txt" className="hidden"
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])} />

        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <SpinnerIcon className="h-7 w-7 text-seed-500" />
            <p className="text-sm text-[#71717a]">Uploading and extracting text…</p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex justify-center">
              <UploadIcon className="h-8 w-8 text-[#52525b]" />
            </div>
            <p className="font-medium text-[#fafafa] text-sm">Drop a document here</p>
            <p className="text-xs text-[#71717a]">or click to browse</p>
            <div className="flex justify-center gap-2 mt-3">
              {["PDF", "TXT"].map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded border border-[#27272a] text-[#71717a]">{t}</span>
              ))}
            </div>
            <p className="text-xs text-[#3f3f46] mt-1">Max 20 MB</p>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-4 rounded-xl bg-seed-950/40 border border-seed-900/50 text-sm text-seed-400">{success}</div>
      )}

      {/* Document list */}
      <div className="mt-8">
        <div className="flex items-center gap-2 mb-4">
          <DatabaseIcon className="h-4 w-4 text-[#52525b]" />
          <h2 className="text-sm font-semibold text-[#71717a]">
            {docs.length === 0 ? "No documents yet" : `${docs.length} document${docs.length === 1 ? "" : "s"}`}
          </h2>
        </div>

        {loading && docs.length === 0 && (
          <p className="text-sm text-[#52525b]">Loading…</p>
        )}

        <div className="space-y-2">
          {docs.map((doc) => (
            <div key={doc.document_id}
              className="flex items-center justify-between p-4 rounded-xl bg-[#111113] border border-[#1c1c1f]"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#fafafa] truncate">{doc.filename}</p>
                <p className="text-xs text-[#52525b] mt-0.5">
                  {formatDate(doc.uploaded_at)} · {formatBytes(doc.text_length)}
                </p>
              </div>
              <span className={`ml-4 shrink-0 text-xs px-2.5 py-0.5 rounded-full border font-medium ${
                STATUS_STYLES[doc.processing_status] ?? STATUS_STYLES.pending
              }`}>
                {doc.processing_status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
