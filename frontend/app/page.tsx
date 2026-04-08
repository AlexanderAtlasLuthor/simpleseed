import Link from "next/link";
import {
  FileTextIcon, ChartBarIcon, PencilIcon, ShieldIcon,
  BuildingIcon, DatabaseIcon, SearchIcon, SparklesIcon,
} from "./components/Icons";

const FEATURES = [
  {
    Icon: SearchIcon,
    title: "Requirement extraction",
    desc: "Every mandatory and optional requirement parsed in seconds — no more manual reading.",
  },
  {
    Icon: ChartBarIcon,
    title: "Calibrated bid scoring",
    desc: "0–100 score with weighted breakdown across relevance, budget fit, and requirements match.",
  },
  {
    Icon: PencilIcon,
    title: "Proposal drafts",
    desc: "A structured proposal grounded in your knowledge base, tailored to each RFP.",
  },
  {
    Icon: ShieldIcon,
    title: "Risk identification",
    desc: "Compliance gaps, tight deadlines, missing budgets — surfaced before you commit.",
  },
  {
    Icon: BuildingIcon,
    title: "SAM.gov search",
    desc: "Search federal contract opportunities and analyze any notice in one click.",
  },
  {
    Icon: DatabaseIcon,
    title: "Knowledge base grounding",
    desc: "Upload past proposals. Every draft is backed by your real experience.",
  },
];

const STEPS = [
  { Icon: FileTextIcon, step: "01", title: "Upload",  desc: "Drop a PDF, paste a URL, or search SAM.gov" },
  { Icon: SparklesIcon, step: "02", title: "Analyze", desc: "AI extracts requirements, risks, and scores the opportunity" },
  { Icon: ChartBarIcon, step: "03", title: "Decide",  desc: "BID / NO BID with clear evidence and reasoning" },
  { Icon: PencilIcon,   step: "04", title: "Propose", desc: "Export a ready-to-edit proposal in Word or PDF" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="relative px-6 pt-24 pb-28 text-center overflow-hidden">
        <div className="pointer-events-none absolute inset-0 flex justify-center">
          <div className="mt-4 h-72 w-[600px] rounded-full bg-seed-950/60 blur-3xl" />
        </div>
        <div className="relative max-w-2xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#27272a] bg-[#18181b] text-[#71717a] text-xs font-medium mb-8 tracking-wide uppercase">
            <span className="w-1.5 h-1.5 rounded-full bg-seed-500 animate-pulse" />
            Powered by Claude AI
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold text-[#fafafa] tracking-tight leading-[1.1] mb-6">
            Win more contracts.<br />
            <span className="text-seed-400">Bid smarter.</span>
          </h1>

          <p className="text-lg text-[#71717a] max-w-lg mx-auto leading-relaxed mb-10">
            AI-powered RFP analysis, bid scoring, and proposal generation
            for consultants and contractors who respond to opportunities regularly.
          </p>

          <div className="flex items-center justify-center gap-3 flex-wrap">
            <Link
              href="/login"
              className="px-7 py-3 rounded-lg bg-seed-600 hover:bg-seed-500 text-white font-semibold text-sm transition-colors"
            >
              Get started
            </Link>
            <Link
              href="/analyze"
              className="px-7 py-3 rounded-lg border border-[#27272a] bg-[#18181b] hover:bg-[#27272a] text-[#fafafa] font-semibold text-sm transition-colors"
            >
              Try without an account
            </Link>
          </div>
        </div>
      </section>

      {/* ── How it works ──────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[#18181b]">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold tracking-widest text-[#52525b] uppercase mb-10">
            How it works
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {STEPS.map(({ Icon, step, title, desc }) => (
              <div key={step} className="text-center">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-[#18181b] border border-[#27272a] mb-4">
                  <Icon className="h-5 w-5 text-seed-400" />
                </div>
                <div className="text-xs font-mono text-[#3f3f46] mb-1">{step}</div>
                <div className="font-semibold text-[#fafafa] text-sm mb-2">{title}</div>
                <div className="text-xs text-[#71717a] leading-relaxed">{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[#18181b]">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold tracking-widest text-[#52525b] uppercase mb-3">
            Capabilities
          </p>
          <h2 className="text-center text-2xl font-bold text-[#fafafa] mb-3">
            Everything you need to bid smarter
          </h2>
          <p className="text-center text-[#71717a] mb-14 max-w-md mx-auto text-sm">
            Built for BD managers and capture teams who need to move fast and win more.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {FEATURES.map(({ Icon, title, desc }) => (
              <div
                key={title}
                className="p-5 rounded-xl border border-[#1c1c1f] bg-[#111113] hover:border-[#27272a] transition-colors"
              >
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="p-1.5 rounded-lg bg-[#18181b] border border-[#27272a]">
                    <Icon className="h-4 w-4 text-seed-400" />
                  </div>
                  <h3 className="font-semibold text-[#fafafa] text-sm">{title}</h3>
                </div>
                <p className="text-xs text-[#71717a] leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[#18181b] text-center">
        <div className="max-w-md mx-auto">
          <h2 className="text-2xl font-bold text-[#fafafa] mb-3">
            Ready to analyze your first RFP?
          </h2>
          <p className="text-[#71717a] text-sm mb-8">
            No setup required. Upload a PDF and get a full analysis in under a minute.
          </p>
          <Link
            href="/analyze"
            className="inline-block px-8 py-3 rounded-lg bg-seed-600 hover:bg-seed-500 text-white font-semibold text-sm transition-colors"
          >
            Start analyzing
          </Link>
        </div>
      </section>
    </div>
  );
}
