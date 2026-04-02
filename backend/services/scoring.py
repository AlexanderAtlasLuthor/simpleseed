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


def score_bid(requirements: dict | str, industry: Optional[str] = None) -> dict:
    from services.industry import get_industry_context
    ctx = get_industry_context(industry)

    if isinstance(requirements, dict):
        req_text = json.dumps(requirements, indent=2)
    else:
        req_text = str(requirements)

    prompt = f"""You are a strategic bid/no-bid advisor. Analyze this RFP and score the opportunity.

VENDOR CONTEXT: {ctx['vendor_type']} — focused on {ctx['focus'][:120]}

Score each factor from 0 to 100:
- "relevance_score" (weight 30%): How relevant is this opportunity for a {ctx['vendor_type']}? \
Consider alignment with their core capabilities and industry focus.
- "budget_fit" (weight 25%): Is the budget realistic and the opportunity worthwhile? If unknown, score 50.
- "requirements_match" (weight 25%): How achievable are the requirements for a capable {ctx['vendor_type']}?
- "completeness" (weight 20%): How clear and complete is the RFP? Vague RFPs = higher risk.

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
        breakdown = _heuristic_score(req_text, ctx)

    weighted = (
        breakdown.get("relevance_score", 50) * 0.30
        + breakdown.get("budget_fit", 50) * 0.25
        + breakdown.get("requirements_match", 50) * 0.25
        + breakdown.get("completeness", 50) * 0.20
    )
    score = round(weighted)

    return {
        "score": score,
        "decision": "BID" if score >= 60 else "NO BID",
        "breakdown": {
            "relevance_score": breakdown.get("relevance_score", 50),
            "budget_fit": breakdown.get("budget_fit", 50),
            "requirements_match": breakdown.get("requirements_match", 50),
            "completeness": breakdown.get("completeness", 50),
        },
        "reasoning": breakdown.get("reasoning", "Score calculated based on RFP analysis."),
    }


def _heuristic_score(text: str, industry_context: dict) -> dict:
    t = text.lower()
    # Use industry-specific domain keywords for relevance detection
    domain_keywords = [d.lower() for d in industry_context.get("relevant_domains", [])]
    # Fall back to generic service keywords if the industry has no domain list (e.g. "general")
    fallback_keywords = ["service", "project", "delivery", "solution", "support", "consulting"]
    keywords = domain_keywords if domain_keywords else fallback_keywords

    return {
        "relevance_score": 70 if any(k in t for k in keywords) else 50,
        "budget_fit": 65 if any(k in t for k in ["budget", "cost", "price", "usd", "eur"]) else 50,
        "requirements_match": 70 if "experience" in t else 55,
        "completeness": 75 if len(text) > 1000 else 45,
        "reasoning": (
            f"Score calculated using heuristic analysis for a {industry_context['vendor_type']}. "
            "Add ANTHROPIC_API_KEY for AI-powered scoring."
        ),
    }
