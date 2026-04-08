"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../../lib/api";

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
  completed: "bg-seed-900/40 border-seed-800/50 text-seed-400",
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
      const res = await apiFetch("/api/knowledge");
      if (res.ok) setDocs(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDocs(); }, []);

  const handleUpload = async (file: File) => {
    setError(null);
    setSuccess(null);

    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "txt"].includes(ext ?? "")) {
      setError("Only PDF and TXT files are supported.");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res  = await apiFetch("/api/knowledge", { method: "POST", body: formData });
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
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const formatBytes = (n: number | null) => {
    if (n === null) return "—";
    if (n < 1000) return `${n} chars`;
    return `${(n / 1000).toFixed(1)}k chars`;
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric",
    });
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-14">
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-[#e8f5eb] tracking-tight mb-2">
          Knowledge Base
        </h1>
        <p className="text-sm text-[#6b8f72]">
          Upload past proposals, case studies, or reference documents. The system
          uses these to improve proposal generation and strategic context.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-200 mb-4
          ${dragging   ? "border-seed-500 bg-seed-500/10 cursor-copy"
          : uploading  ? "border-[#1e2d22] bg-[#0a0f0d] cursor-wait"
          : "border-[#1e2d22] hover:border-seed-700 hover:bg-[#111a14] cursor-pointer"}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <svg className="animate-spin h-8 w-8 text-seed-500" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            <p className="text-sm text-[#6b8f72]">Uploading and extracting text…</p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-4xl">📚</div>
            <p className="font-medium text-[#e8f5eb]">Drop a document here</p>
            <p className="text-sm text-[#6b8f72]">or click to browse</p>
            <div className="flex justify-center gap-2 mt-3">
              {["PDF", "TXT"].map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded border border-[#1e2d22] text-[#6b8f72]">
                  {t}
                </span>
              ))}
            </div>
            <p className="text-xs text-[#3d5c44] mt-1">Max 20 MB</p>
          </div>
        )}
      </div>

      {/* Feedback banners */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-6 p-4 rounded-xl bg-seed-900/30 border border-seed-800/50 text-sm text-seed-400">
          {success}
        </div>
      )}

      {/* Document list */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-[#6b8f72] uppercase tracking-widest mb-4">
          {docs.length === 0 ? "No documents yet" : `${docs.length} document${docs.length === 1 ? "" : "s"}`}
        </h2>

        {loading && docs.length === 0 && (
          <p className="text-sm text-[#3d5c44]">Loading…</p>
        )}

        <div className="space-y-3">
          {docs.map((doc) => (
            <div
              key={doc.document_id}
              className="flex items-center justify-between p-4 rounded-xl bg-[#0d1610] border border-[#1e2d22]"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#e8f5eb] truncate">{doc.filename}</p>
                <p className="text-xs text-[#3d5c44] mt-0.5">
                  {formatDate(doc.uploaded_at)} · {formatBytes(doc.text_length)}
                </p>
              </div>
              <span
                className={`ml-4 shrink-0 text-xs px-2 py-0.5 rounded border font-medium
                  ${STATUS_STYLES[doc.processing_status] ?? STATUS_STYLES.pending}`}
              >
                {doc.processing_status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
