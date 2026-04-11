"""
Bid scoring service — 1.3 Explainable Scoring.

Design principles
-----------------
Separation of concerns
  Numeric scoring and explanation generation happen in one LLM call, but
  the weighted-sum calculation is always done deterministically in Python.
  The LLM provides factor scores and explanatory text; Python owns the math.

Determinism
  score = round(sum(factor_score[k] * weight[k] for k in factors))
  This calculation is always performed here — the LLM cannot alter it.

Explainability
  Each factor returns a numeric score, weight, one-sentence explanation,
  and evidence grounded in the RFP text.  Strengths, risks, and a summary
  explanation are generated in the same LLM call so they are consistent
  with the numeric scores.

Backward compatibility
  The existing fields (score, decision, breakdown, reasoning, weights_used,
  threshold_used) are unchanged.  New fields are added alongside.

Heuristic fallback
  If the LLM call fails or the API key is absent, _heuristic_score()
  produces all the same fields using keyword analysis.  Scores are
  conservative; confidence is always "low" in heuristic mode.
"""
import json
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


# ── LLM prompt ────────────────────────────────────────────────────────────────

_SCORING_PROMPT = """You are a strategic bid/no-bid advisor. Analyze this RFP and score the opportunity.

VENDOR CONTEXT: {vendor_type} — focused on {focus}

Score each factor from 0 to 100:
  - "relevance_score"    (weight {w_relevance:.0%}): How relevant is this for a {vendor_type}?
  - "budget_fit"         (weight {w_budget:.0%}): Is the budget realistic? If unspecified, score 50.
  - "requirements_match" (weight {w_requirements:.0%}): How achievable are the requirements?
  - "completeness"       (weight {w_completeness:.0%}): How clear and complete is the RFP?

IMPORTANT: Score based strictly on what is present in the RFP. Scores are integers 0–100.
Do not inflate scores to sound optimistic. Low scores are informative.

RFP DATA:
{req_text}

Return a JSON object with exactly these fields:
{{
  "relevance_score": <integer 0-100>,
  "relevance_explanation": "<1 sentence: why this score>",
  "relevance_evidence": "<direct quote or phrase from RFP, or 'Not stated'>",

  "budget_fit": <integer 0-100>,
  "budget_fit_explanation": "<1 sentence: why this score>",
  "budget_fit_evidence": "<budget figure from RFP, or 'Not specified'>",

  "requirements_match": <integer 0-100>,
  "requirements_match_explanation": "<1 sentence: why this score>",
  "requirements_match_evidence": "<key requirement text, or 'Not stated'>",

  "completeness": <integer 0-100>,
  "completeness_explanation": "<1 sentence: why this score>",
  "completeness_evidence": "<specific completeness signal, or 'N/A'>",

  "strengths": ["<positive signal 1>", "<positive signal 2>"],
  "risks": ["<scoring risk or uncertainty 1>", "<scoring risk or uncertainty 2>"],
  "summary_explanation": "<2-3 sentences explaining the overall recommendation>",
  "confidence": "high" | "medium" | "low",
  "missing_inputs": ["<RFP element that is absent and would sharpen confidence>"],
  "reasoning": "<2-3 sentence summary for backward compatibility>"
}}

RULES:
- strengths and risks: short phrases (max 15 words each), at most 3 items each.
- missing_inputs: list of specific absent RFP sections that affect score accuracy.
- confidence: "low" when key fields (budget, scope, evaluation criteria) are missing;
              "medium" when the RFP is partial but workable; "high" when RFP is complete.
- Do NOT let explanation quality influence the numeric scores.
- Return only valid JSON. No markdown."""


# ── Public API ────────────────────────────────────────────────────────────────

def score_bid(requirements: dict | str, industry: Optional[str] = None) -> dict:
    """
    Score an RFP opportunity and return an explainable scoring object.

    Returns a dict with:
      Core (unchanged from 1.2):
        score, decision, breakdown, reasoning, weights_used, threshold_used
      New in 1.3 (explainability):
        factor_details, strengths, risks, summary_explanation, confidence,
        missing_inputs
    """
    from services.industry import get_industry_context
    from services.scoring_config import load_scoring_config

    cfg = load_scoring_config()
    weights   = cfg["weights"]
    threshold = float(cfg["bid_threshold"])
    ind_ctx   = get_industry_context(industry)

    req_text = json.dumps(requirements, indent=2) if isinstance(requirements, dict) else str(requirements)

    prompt = _SCORING_PROMPT.format(
        vendor_type    = ind_ctx["vendor_type"],
        focus          = ind_ctx["focus"][:120],
        w_relevance    = weights["relevance_score"],
        w_budget       = weights["budget_fit"],
        w_requirements = weights["requirements_match"],
        w_completeness = weights["completeness"],
        req_text       = req_text[:4000],
    )

    try:
        message = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        breakdown = json.loads(content)
    except Exception:
        breakdown = _heuristic_score(req_text, ind_ctx)

    # ── Deterministic weighted sum — LLM cannot alter this ────────────────────
    factor_scores = {
        "relevance_score":    _clamp(breakdown.get("relevance_score",    50)),
        "budget_fit":         _clamp(breakdown.get("budget_fit",         50)),
        "requirements_match": _clamp(breakdown.get("requirements_match", 50)),
        "completeness":       _clamp(breakdown.get("completeness",       50)),
    }
    weighted = sum(factor_scores[k] * weights[k] for k in factor_scores)
    score    = _clamp(round(weighted))

    # ── Assemble per-factor detail (explanation is read-only, never re-scores) ─
    factor_details = {
        "relevance_score": {
            "score":       factor_scores["relevance_score"],
            "weight":      weights["relevance_score"],
            "explanation": str(breakdown.get("relevance_explanation", "")),
            "evidence":    str(breakdown.get("relevance_evidence", "")),
        },
        "budget_fit": {
            "score":       factor_scores["budget_fit"],
            "weight":      weights["budget_fit"],
            "explanation": str(breakdown.get("budget_fit_explanation", "")),
            "evidence":    str(breakdown.get("budget_fit_evidence", "")),
        },
        "requirements_match": {
            "score":       factor_scores["requirements_match"],
            "weight":      weights["requirements_match"],
            "explanation": str(breakdown.get("requirements_match_explanation", "")),
            "evidence":    str(breakdown.get("requirements_match_evidence", "")),
        },
        "completeness": {
            "score":       factor_scores["completeness"],
            "weight":      weights["completeness"],
            "explanation": str(breakdown.get("completeness_explanation", "")),
            "evidence":    str(breakdown.get("completeness_evidence", "")),
        },
    }

    return {
        # ── Core (backward-compatible) ────────────────────────────────────────
        "score":          score,
        "decision":       "BID" if score >= threshold else "NO BID",
        "breakdown":      factor_scores,
        "reasoning":      str(breakdown.get("reasoning", "Score calculated based on RFP analysis.")),
        "weights_used":   dict(weights),
        "threshold_used": threshold,
        # ── Explainability (1.3) ──────────────────────────────────────────────
        "factor_details":      factor_details,
        "strengths":           _safe_list(breakdown.get("strengths")),
        "risks":               _safe_list(breakdown.get("risks")),
        "summary_explanation": str(breakdown.get("summary_explanation", "")),
        "confidence":          _safe_confidence(breakdown.get("confidence")),
        "missing_inputs":      _safe_list(breakdown.get("missing_inputs")),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(v, lo: int = 0, hi: int = 100) -> int:
    """Coerce v to an integer in [lo, hi]; default 50 on parse failure."""
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return 50


def _safe_list(v) -> list[str]:
    """Return a list of non-empty strings regardless of input type."""
    if isinstance(v, list):
        return [str(item) for item in v if item]
    return []


def _safe_confidence(v) -> str:
    return v if v in ("high", "medium", "low") else "medium"


# ── Heuristic fallback ────────────────────────────────────────────────────────

def _heuristic_score(text: str, industry_context: dict) -> dict:
    """
    Keyword-based scoring used when the LLM is unavailable.

    Produces the full explainability schema so callers always get the same
    output shape regardless of which path ran. Confidence is always "low"
    in heuristic mode because keyword analysis is coarse.
    """
    t = text.lower()
    domain_keywords  = [d.lower() for d in industry_context.get("relevant_domains", [])]
    fallback_kws     = ["service", "project", "delivery", "solution", "support", "consulting"]
    keywords         = domain_keywords if domain_keywords else fallback_kws

    kw_hit      = any(k in t for k in keywords)
    has_budget  = any(k in t for k in ["budget", "cost", "price", "usd", "eur", "contract value"])
    has_exp     = "experience" in t
    is_long     = len(text) > 1000

    relevance    = 70 if kw_hit     else 50
    budget_fit   = 65 if has_budget else 50
    req_match    = 70 if has_exp    else 55
    completeness = 75 if is_long    else 45

    missing: list[str] = []
    if not has_budget:
        missing.append("Budget or price ceiling not specified")
    if not is_long:
        missing.append("Document is short — scope may be incomplete")

    strengths: list[str] = []
    if kw_hit:
        strengths.append("Domain-relevant keywords detected in document")
    if has_budget:
        strengths.append("Budget information is present")

    scoring_risks: list[str] = []
    if not has_budget:
        scoring_risks.append("No budget found — pricing confidence is low")
    if not is_long:
        scoring_risks.append("Short document — completeness score is conservative")

    vendor = industry_context.get("vendor_type", "vendor")
    return {
        "relevance_score": relevance,
        "relevance_explanation": (
            "Domain keywords matched."
            if kw_hit else "No domain keywords found; relevance is uncertain."
        ),
        "relevance_evidence": "Keyword scan (heuristic — set ANTHROPIC_API_KEY for AI scoring)",

        "budget_fit": budget_fit,
        "budget_fit_explanation": (
            "Budget indicators found in document."
            if has_budget else "Budget not specified; conservative score applied."
        ),
        "budget_fit_evidence": "Budget keywords present." if has_budget else "Not specified",

        "requirements_match": req_match,
        "requirements_match_explanation": (
            "Experience-related terms found in requirements."
            if has_exp else "Requirement specificity is unclear from text analysis."
        ),
        "requirements_match_evidence": (
            "Keyword 'experience' present." if has_exp else "Not detected"
        ),

        "completeness": completeness,
        "completeness_explanation": (
            "Document length suggests a reasonably complete RFP."
            if is_long else "Short document — RFP may be incomplete."
        ),
        "completeness_evidence": f"Document length: {len(text)} characters",

        "strengths":      strengths,
        "risks":          scoring_risks,
        "summary_explanation": (
            f"Score computed via heuristic analysis for a {vendor}. "
            "Set ANTHROPIC_API_KEY for AI-powered scoring with full explanations."
        ),
        "confidence":     "low",
        "missing_inputs": missing,
        "reasoning": (
            f"Heuristic score for a {vendor}. "
            "Add ANTHROPIC_API_KEY for AI-powered analysis."
        ),
    }
