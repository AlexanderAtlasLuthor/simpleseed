import Link from "next/link";

interface Props {
  id: string;
  filename: string;
  score: number;
  decision: string;
  summary?: string;
  created_at: string;
  onDelete?: (id: string) => void;
}

export default function RFPCard({ id, filename, score, decision, summary, created_at, onDelete }: Props) {
  const isBid = decision === "BID";
  const scoreColor =
    score >= 70 ? "text-seed-400" : score >= 50 ? "text-yellow-400" : "text-red-400";
  const date = new Date(created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="group rounded-xl border border-[#1e2d22] bg-[#111a14] hover:border-seed-800 transition-colors p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <Link href={`/analysis/${id}`}>
            <p className="font-medium text-[#e8f5eb] truncate hover:text-seed-400 transition-colors cursor-pointer">
              {filename}
            </p>
          </Link>
          {summary && (
            <p className="text-xs text-[#6b8f72] mt-1 line-clamp-2 leading-relaxed">
              {summary}
            </p>
          )}
          <p className="text-xs text-[#6b8f72] mt-2">{date}</p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="text-right">
            <div className={`text-xl font-bold font-mono ${scoreColor}`}>{score}</div>
            <div
              className={`text-xs font-medium mt-0.5 ${
                isBid ? "text-seed-500" : "text-red-500"
              }`}
            >
              {decision}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Link
              href={`/analysis/${id}`}
              className="text-xs px-2.5 py-1 rounded-lg bg-[#1e2d22] text-[#6b8f72] hover:bg-seed-900/40 hover:text-seed-400 transition-colors"
            >
              View
            </Link>
            {onDelete && (
              <button
                onClick={() => onDelete(id)}
                className="text-xs px-2.5 py-1 rounded-lg bg-[#1e2d22] text-[#6b8f72] hover:bg-red-950/40 hover:text-red-400 transition-colors"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
