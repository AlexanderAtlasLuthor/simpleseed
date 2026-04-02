"use client";
import { useState } from "react";

interface Props {
  proposal: string;
}

export default function ProposalView({ proposal }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(proposal);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Render basic markdown-ish formatting
  const lines = proposal.split("\n");
  const rendered = lines.map((line, i) => {
    if (/^#{1,3}\s/.test(line)) {
      const text = line.replace(/^#+\s/, "");
      return (
        <h3 key={i} className="text-seed-300 font-semibold text-base mt-5 mb-2">
          {text}
        </h3>
      );
    }
    if (line.startsWith("- ") || line.startsWith("• ")) {
      return (
        <li key={i} className="ml-4 text-sm text-[#d1fae5] leading-relaxed list-disc">
          {line.replace(/^[-•]\s/, "")}
        </li>
      );
    }
    if (line.trim() === "") {
      return <div key={i} className="h-2" />;
    }
    return (
      <p key={i} className="text-sm text-[#d1fae5] leading-relaxed">
        {line}
      </p>
    );
  });

  return (
    <div className="rounded-2xl border border-[#1e2d22] bg-[#111a14] overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#1e2d22]">
        <p className="text-xs uppercase tracking-widest text-[#6b8f72]">
          Proposal Draft
        </p>
        <button
          onClick={handleCopy}
          className="text-xs px-3 py-1.5 rounded-lg border border-[#1e2d22] text-[#6b8f72] hover:border-seed-700 hover:text-seed-400 transition-colors"
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <div className="p-6 max-h-[600px] overflow-y-auto space-y-1">
        {rendered}
      </div>
    </div>
  );
}
