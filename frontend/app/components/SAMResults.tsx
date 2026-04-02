"use client";

interface Opportunity {
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

interface Props {
  opportunities: Opportunity[];
  total: number;
  onAnalyze: (noticeId: string, title: string) => void;
  analyzing: string | null; // noticeId currently being analyzed
}

export default function SAMResults({ opportunities, total, onAnalyze, analyzing }: Props) {
  if (!opportunities.length) {
    return (
      <div className="text-center py-12 text-[#6b8f72]">
        <div className="text-3xl mb-3">🔍</div>
        <p>No active opportunities found. Try different keywords.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[#6b8f72]">
          Showing <span className="text-seed-400">{opportunities.length}</span> of{" "}
          <span className="text-seed-400">{total.toLocaleString()}</span> opportunities
        </p>
        <a
          href="https://sam.gov/search/?index=opp"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-[#6b8f72] hover:text-seed-400 underline"
        >
          View all on SAM.gov ↗
        </a>
      </div>

      {opportunities.map((opp) => {
        const isAnalyzing = analyzing === opp.noticeId;
        const deadline = opp.responseDeadLine
          ? new Date(opp.responseDeadLine).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
          : null;

        return (
          <div
            key={opp.noticeId}
            className="rounded-xl border border-[#1e2d22] bg-[#111a14] p-4 hover:border-seed-800 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="font-medium text-[#e8f5eb] text-sm leading-snug">{opp.title}</p>
                {opp.agency && (
                  <p className="text-xs text-[#6b8f72] mt-1 truncate">{opp.agency}</p>
                )}
                <div className="flex flex-wrap gap-2 mt-2">
                  {opp.type && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#0a0f0d] border border-[#1e2d22] text-[#6b8f72]">
                      {opp.type}
                    </span>
                  )}
                  {opp.naicsCode && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#0a0f0d] border border-[#1e2d22] text-[#6b8f72]">
                      NAICS {opp.naicsCode}
                    </span>
                  )}
                  {opp.setAside && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-seed-900/30 border border-seed-800/30 text-seed-600">
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
                      ? "bg-seed-900/40 text-seed-500 border border-seed-800"
                      : analyzing
                      ? "bg-[#1e2d22] text-[#6b8f72] cursor-not-allowed"
                      : "bg-seed-700 hover:bg-seed-600 text-white"
                  }`}
                >
                  {isAnalyzing ? (
                    <span className="flex items-center gap-1.5">
                      <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Analyzing
                    </span>
                  ) : "Analyze"}
                </button>
                <a
                  href={opp.uiLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs px-3 py-1.5 rounded-lg border border-[#1e2d22] text-[#6b8f72] hover:text-seed-400 hover:border-seed-800 transition-colors text-center"
                >
                  View ↗
                </a>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
