"use client";
import { useRef, useState } from "react";

interface Props {
  onAnalyze: (file: File) => void;
  loading: boolean;
}

export default function UploadZone({ onAnalyze, loading }: Props) {
  const [dragging, setDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("Please upload a PDF file.");
      return;
    }
    setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleSubmit = () => {
    if (selectedFile) onAnalyze(selectedFile);
  };

  return (
    <div className="w-full max-w-xl mx-auto">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !selectedFile && inputRef.current?.click()}
        className={`
          relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer
          transition-all duration-200
          ${dragging
            ? "border-seed-500 bg-seed-500/10"
            : selectedFile
            ? "border-seed-600 bg-seed-900/20 cursor-default"
            : "border-[#1e2d22] hover:border-seed-700 hover:bg-[#111a14]"
          }
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />

        {selectedFile ? (
          <div className="space-y-3">
            <div className="text-4xl">📄</div>
            <p className="font-medium text-[#e8f5eb]">{selectedFile.name}</p>
            <p className="text-sm text-[#6b8f72]">
              {(selectedFile.size / 1024).toFixed(1)} KB
            </p>
            <button
              onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}
              className="text-xs text-[#6b8f72] hover:text-red-400 underline"
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-4xl">📂</div>
            <p className="font-medium text-[#e8f5eb]">Drop your RFP here</p>
            <p className="text-sm text-[#6b8f72]">or click to browse — PDF only</p>
          </div>
        )}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!selectedFile || loading}
        className={`
          mt-4 w-full py-3 rounded-xl font-semibold text-sm transition-all duration-200
          ${selectedFile && !loading
            ? "bg-seed-600 hover:bg-seed-500 text-white shadow-lg shadow-seed-900/50"
            : "bg-[#1e2d22] text-[#6b8f72] cursor-not-allowed"
          }
        `}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Analyzing RFP...
          </span>
        ) : (
          "Analyze RFP"
        )}
      </button>
    </div>
  );
}
