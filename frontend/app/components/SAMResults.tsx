"use client";
import { SearchIcon, SpinnerIcon, ExternalLinkIcon } from "./Icons";

interface Opportunity {
  noticeId: string; title: string; agency: string; type: string;
  naicsCode: string; postedDate: string; responseDeadLine: string;
  setAside: string; uiLink: string;
}

interface Props {
  opportunities: Opportunity[];
  total: number;
  onAnalyze: (noticeId: string, title: string) => void;
  analyzing: string | null;
}

export default function SAMResults({ opportunities, total, onAnalyze, analyzing }: Props) {
  if (!opportunities.length) {
    return (
      <div className="text-center py-12 text-[#71717a]">
        <div className="flex justify-center mb-3">
          <SearchIcon className="h-8 w-8 text-[#3f3f46]" />
        </div>
        <p className="text-sm">No active opportunities found. Try different keywords.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[#71717a]">
          Showing <span className="text-[#fafafa]">{opportunities.length}</span> of{" "}
          <span className="text-[#fafafa]">{total.toLocaleString()}</span> opportunities
        </p>
        <a href="https://sam.gov/search/?index=opp" target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-[#71717a] hover:text-seed-400 transition-colors">
          View all on SAM.gov
          <ExternalLinkIcon className="h-3 w-3" />
        </a>
      </div>

      {opportunities.map((opp) => {
        const isAnalyzing = analyzing === opp.noticeId;
        const deadline = opp.responseDeadLine
          ? new Date(opp.responseDeadLine).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
          : null;

        return (
          <div key={opp.noticeId}
            className="rounded-xl border border-[#1c1c1f] bg-[#111113] p-4 hover:border-[#27272a] transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="font-medium text-[#fafafa] text-sm leading-snug">{opp.title}</p>
                {opp.agency && <p className="text-xs text-[#71717a] mt-1 truncate">{opp.agency}</p>}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {opp.type && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#18181b] border border-[#27272a] text-[#71717a]">
                      {opp.type}
                    </span>
                  )}
                  {opp.naicsCode && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#18181b] border border-[#27272a] text-[#71717a]">
                      NAICS {opp.naicsCode}
                    </span>
                  )}
                  {opp.setAside && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-seed-950/40 border border-seed-900/40 text-seed-500">
                      {opp.setAside}
                    </span>
                  )}
                  {deadline && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-950/30 border border-yellow-900/30 text-yellow-600">
                      Due {deadline}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-1.5 shrink-0">
                <button
                  onClick={() => onAnalyze(opp.noticeId, opp.title)}
                  disabled={!!analyzing}
                  className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                    isAnalyzing
                      ? "bg-seed-950/40 text-seed-500 border border-seed-900"
                      : analyzing
                      ? "bg-[#18181b] text-[#52525b] cursor-not-allowed border border-[#27272a]"
                      : "bg-seed-600 hover:bg-seed-500 text-white"
                  }`}
                >
                  {isAnalyzing
                    ? <span className="flex items-center gap-1.5"><SpinnerIcon className="h-3 w-3" /> Analyzing</span>
                    : "Analyze"}
                </button>
                <a href={opp.uiLink} target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-[#27272a] text-[#71717a] hover:text-[#fafafa] hover:border-[#3f3f46] transition-colors">
                  View <ExternalLinkIcon className="h-3 w-3" />
                </a>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
