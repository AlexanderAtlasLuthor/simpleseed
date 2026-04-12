import json
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

def get_client():
    from services.observability import get_anthropic_client, set_service
    set_service("scoring")
    return get_anthropic_client()


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

    prompt = f"""You are a strategic bid/no-bid advisor. Analyze this RFP and score the opportunity.

VENDOR CONTEXT: {ind_ctx['vendor_type']} — focused on {ind_ctx['focus'][:120]}

Score each factor from 0 to 100:
- "relevance_score" (weight {weights['relevance_score']:.0%}): How relevant is this opportunity \
for a {ind_ctx['vendor_type']}? Consider alignment with their core capabilities and industry focus.
- "budget_fit" (weight {weights['budget_fit']:.0%}): Is the budget realistic and the opportunity \
worthwhile? If unknown, score 50.
- "requirements_match" (weight {weights['requirements_match']:.0%}): How achievable are the \
requirements for a capable {ind_ctx['vendor_type']}?
- "completeness" (weight {weights['completeness']:.0%}): How clear and complete is the RFP? \
Vague RFPs = higher risk.

RFP DATA:
{req_text[:4000]}

Return a JSON object with exactly these fields:
{{
  "relevance_score": <integer 0-100>,
  "budget_fit": <integer 0-100>,
  "requirements_match": <integer 0-100>,
  "completeness": <integer 0-100>,
  "reasoning": "<2-3 sentences explaining the recommendation>"
}}

Return only valid JSON. No markdown."""

    try:
        message = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
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

    weighted = (
        breakdown.get("relevance_score",    50) * weights["relevance_score"]
        + breakdown.get("budget_fit",       50) * weights["budget_fit"]
        + breakdown.get("requirements_match", 50) * weights["requirements_match"]
        + breakdown.get("completeness",     50) * weights["completeness"]
    )
    score = round(weighted)

    return {
        "score": score,
        "decision": "BID" if score >= threshold else "NO BID",
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
        "relevance_score":    70 if any(k in t for k in keywords) else 50,
        "budget_fit":         65 if any(k in t for k in ["budget", "cost", "price", "usd", "eur"]) else 50,
        "requirements_match": 70 if "experience" in t else 55,
        "completeness":       75 if len(text) > 1000 else 45,
        "reasoning": (
            f"Score calculated using heuristic analysis for a {industry_context['vendor_type']}. "
            "Add ANTHROPIC_API_KEY for AI-powered scoring."
        ),
    }
