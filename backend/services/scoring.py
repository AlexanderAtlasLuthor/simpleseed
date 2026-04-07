import json
import logging
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv
from settings import llm_model

load_dotenv()

logger = logging.getLogger(__name__)
_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def score_bid(requirements: dict | str, industry: Optional[str] = None) -> dict:
    from services.industry import get_industry_context
    from services.scoring_config import load_scoring_config

    ctx = load_scoring_config()
    weights = ctx["weights"]
    threshold = float(ctx["bid_threshold"])

    ind_ctx = get_industry_context(industry)

    if isinstance(requirements, dict):
        req_text = json.dumps(requirements, indent=2)
    else:
        req_text = str(requirements)

    prompt = f"""You are a skeptical bid/no-bid advisor. Protect the vendor from work they cannot win or deliver profitably. \
Default to conservative scores — a score above 70 requires clear, explicit evidence in the RFP.

VENDOR: {ind_ctx['vendor_type']} — focused on {ind_ctx['focus'][:120]}

SCORING RUBRIC (apply to every factor):
  0–20  Disqualifying concern or critical information missing
  21–40 Significant gaps or weaknesses
  41–60 Average — some alignment but notable concerns
  61–75 Good fit with minor gaps (requires evidence)
  76–90 Strong fit with clear explicit evidence
  91–100 Exceptional — rarely warranted

Score each factor:
- "relevance_score" (weight {weights['relevance_score']:.0%}): Does this RFP fall squarely within \
the vendor's core expertise? Penalize heavily for specialized domains, regulated sectors, or tech stacks \
not aligned with their focus.
- "budget_fit" (weight {weights['budget_fit']:.0%}): Is the budget explicitly stated AND realistic? \
Score 35 if budget is absent entirely. Penalize if scope appears severely over- or under-priced.
- "requirements_match" (weight {weights['requirements_match']:.0%}): Can the vendor satisfy ALL \
mandatory requirements? Score 40 if any must-have requirement (certification, clearance, specialized \
skill) is likely unattainable for this vendor type.
- "completeness" (weight {weights['completeness']:.0%}): Are timeline, deliverables, and evaluation \
criteria explicitly defined? Score below 50 if timeline or success criteria are missing — vague RFPs \
increase delivery and payment risk.

RFP DATA:
{req_text[:4000]}

Return a JSON object with exactly these fields:
{{
  "relevance_score": <integer 0-100>,
  "budget_fit": <integer 0-100>,
  "requirements_match": <integer 0-100>,
  "completeness": <integer 0-100>,
  "reasoning": "<2-3 sentences. Cite the strongest signal FOR and AGAINST bidding.>"
}}

Return only valid JSON. No markdown."""

    try:
        logger.debug("LLM call score_bid model=%s", llm_model)
        message = get_client().messages.create(
            model=llm_model,
            max_tokens=400,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        content = message.content[0].text
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        breakdown = json.loads(content)
    except Exception as exc:
        logger.warning(
            "LLM scoring failed (%s) — falling back to heuristic scorer", exc
        )
        breakdown = _heuristic_score(req_text, ind_ctx)

    weighted = (
        breakdown.get("relevance_score",    50) * weights["relevance_score"]
        + breakdown.get("budget_fit",       50) * weights["budget_fit"]
        + breakdown.get("requirements_match", 50) * weights["requirements_match"]
        + breakdown.get("completeness",     50) * weights["completeness"]
    )
    score = round(weighted)

    decision = "BID" if score >= threshold else "NO BID"
    logger.debug(
        "Scoring result score=%d decision=%s threshold=%d "
        "relevance=%s budget=%s match=%s completeness=%s",
        score, decision, threshold,
        breakdown.get("relevance_score"), breakdown.get("budget_fit"),
        breakdown.get("requirements_match"), breakdown.get("completeness"),
    )
    return {
        "score": score,
        "decision": decision,
        "breakdown": {
            "relevance_score":    breakdown.get("relevance_score",    50),
            "budget_fit":         breakdown.get("budget_fit",         50),
            "requirements_match": breakdown.get("requirements_match", 50),
            "completeness":       breakdown.get("completeness",       50),
        },
        "reasoning": breakdown.get("reasoning", "Score calculated based on RFP analysis."),
        "weights_used": dict(weights),
        "threshold_used": threshold,
    }


def _heuristic_score(text: str, industry_context: dict) -> dict:
    t = text.lower()
    domain_keywords = [d.lower() for d in industry_context.get("relevant_domains", [])]
    fallback_keywords = ["service", "project", "delivery", "solution", "support", "consulting"]
    keywords = domain_keywords if domain_keywords else fallback_keywords

    return {
        "relevance_score":    60 if any(k in t for k in keywords) else 40,
        "budget_fit":         55 if any(k in t for k in ["budget", "cost", "price", "usd", "eur"]) else 35,
        "requirements_match": 58 if "experience" in t else 45,
        "completeness":       60 if len(text) > 1000 else 35,
        "reasoning": (
            f"Score calculated using heuristic analysis for a {industry_context['vendor_type']}. "
            "Add ANTHROPIC_API_KEY for AI-powered scoring."
        ),
    }
