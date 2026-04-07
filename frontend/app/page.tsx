import Link from "next/link";

const FEATURES = [
  {
    icon: "🔍",
    title: "Instant requirement extraction",
    desc: "AI parses every mandatory and optional requirement from any RFP in seconds — no more manual reading.",
  },
  {
    icon: "📊",
    title: "Calibrated bid scoring",
    desc: "Get a 0–100 bid score with weighted breakdown across relevance, budget fit, and requirements match.",
  },
  {
    icon: "✍️",
    title: "Proposal drafts, ready to ship",
    desc: "A structured proposal grounded in your knowledge base — tailored to the RFP, not a generic template.",
  },
  {
    icon: "⚠️",
    title: "Risk identification",
    desc: "Compliance gaps, tight deadlines, missing budgets — flagged before you commit to bidding.",
  },
  {
    icon: "🏛️",
    title: "SAM.gov search built-in",
    desc: "Search federal opportunities directly from the app. Analyze any contract notice in one click.",
  },
  {
    icon: "📁",
    title: "Knowledge base grounding",
    desc: "Upload past proposals and capability statements. Every draft is backed by your actual experience.",
  },
];

const STEPS = [
  { step: "01", icon: "📄", title: "Upload",  desc: "Drop a PDF, paste a URL, or search SAM.gov" },
  { step: "02", icon: "🧠", title: "Analyze", desc: "AI extracts requirements, risks, and scores the bid" },
  { step: "03", icon: "📊", title: "Decide",  desc: "BID / NO BID recommendation with clear reasoning" },
  { step: "04", icon: "✍️", title: "Propose", desc: "Export a ready-to-customize proposal in Word or PDF" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden px-6 pt-24 pb-32 text-center">
        {/* Subtle radial glow */}
        <div className="pointer-events-none absolute inset-0 flex items-start justify-center">
          <div className="mt-8 h-96 w-96 rounded-full bg-seed-900/30 blur-3xl" />
        </div>

        <div className="relative z-10 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-seed-800/60 bg-seed-900/20 text-seed-400 text-xs font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-seed-500 animate-pulse" />
            Powered by Claude AI
          </div>

          <h1 className="text-6xl font-bold text-[#e8f5eb] tracking-tight leading-tight mb-6">
            Win more RFPs.
            <br />
            <span className="text-seed-400">Faster.</span>
          </h1>

          <p className="text-xl text-[#6b8f72] max-w-xl mx-auto leading-relaxed mb-10">
            AI-powered RFP analysis, bid scoring, risk identification, and proposal
            generation — from upload to export in under a minute.
          </p>

          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link
              href="/login"
              className="px-8 py-3.5 rounded-xl bg-seed-600 hover:bg-seed-500 text-white font-semibold text-sm transition-colors"
            >
              Get started free
            </Link>
            <Link
              href="/analyze"
              className="px-8 py-3.5 rounded-xl border border-[#1e3022] bg-[#0d1610] hover:border-seed-800 text-[#e8f5eb] font-semibold text-sm transition-colors"
            >
              Try without signing in →
            </Link>
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[#1e2d22]">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-center text-2xl font-bold text-[#e8f5eb] mb-14">
            From PDF to proposal in 4 steps
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {STEPS.map(({ step, icon, title, desc }) => (
              <div key={step} className="text-center">
                <div className="text-4xl mb-4">{icon}</div>
                <div className="text-xs font-mono text-seed-600 mb-1">{step}</div>
                <div className="font-semibold text-[#e8f5eb] text-sm mb-2">{title}</div>
                <div className="text-xs text-[#6b8f72] leading-relaxed">{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features grid ────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[#1e2d22]">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-center text-2xl font-bold text-[#e8f5eb] mb-4">
            Everything you need to bid smarter
          </h2>
          <p className="text-center text-[#6b8f72] mb-14 max-w-xl mx-auto">
            Built for consultants, contractors, and agencies who respond to RFPs regularly.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {FEATURES.map(({ icon, title, desc }) => (
              <div
                key={title}
                className="p-6 rounded-2xl border border-[#1e2d22] bg-[#0d1610] hover:border-seed-900 transition-colors"
              >
                <div className="text-2xl mb-4">{icon}</div>
                <h3 className="font-semibold text-[#e8f5eb] text-sm mb-2">{title}</h3>
                <p className="text-xs text-[#6b8f72] leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA banner ───────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[#1e2d22] text-center">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold text-[#e8f5eb] mb-4">
            Ready to win your next contract?
          </h2>
          <p className="text-[#6b8f72] mb-8">
            Start analyzing RFPs in seconds. No setup required.
          </p>
          <Link
            href="/login"
            className="inline-block px-10 py-4 rounded-xl bg-seed-600 hover:bg-seed-500 text-white font-semibold transition-colors"
          >
            Get started →
          </Link>
        </div>
      </section>
    </div>
  );
}
