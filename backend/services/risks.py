"""
Risk identification service.

Takes structured RFP extraction output and returns a list of bid risks,
each with title, description, severity, category, and evidence grounded
in the RFP content.

Risks are NEVER invented without evidence. When no API key is available,
a keyword-based heuristic fallback runs instead.
"""
import json
import logging
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
_client = None

# ── Schema constraints ────────────────────────────────────────────────────────

VALID_SEVERITIES = {"low", "medium", "high"}

VALID_CATEGORIES = {
    "deadline",       # tight timelines, short submission windows, aggressive schedules
    "compliance",     # regulatory certs required (ISO, HIPAA, FedRAMP, CMMC, SOC 2, etc.)
    "technical",      # complex/unusual technical requirements, performance demands
    "pricing",        # insufficient/unclear budget, fixed-price with open scope
    "capacity",       # scope exceeds typical team, resource-intensive staffing
    "eligibility",    # certifications/licenses/clearances required to be eligible
    "documentation",  # many required attachments, notarizations, complex submission rules
    "scope",          # vague, expanding, or contradictory scope; unclear deliverables
    "competition",    # incumbent signals, sole-source language, pre-selected vendor hints
}

# ── LLM prompt ────────────────────────────────────────────────────────────────

_RISK_PROMPT = """\
You are a bid strategy advisor. Analyze the RFP data below and identify risks \
that a {vendor_type} must consider before deciding to bid.

Return a JSON object with a single key "risks" containing an array. \
Each element must have exactly these fields:
{{
  "title": string — short name for the risk (5-10 words max),
  "description": string — what the risk is and why it matters for the bid decision,
  "severity": "low" | "medium" | "high",
  "category": one of: deadline | compliance | technical | pricing | capacity | eligibility | documentation | scope | competition,
  "evidence": string — direct quote or close paraphrase from the RFP that supports this risk
}}

SEVERITY RULES:
- "high"  — could alone disqualify the bid or cause significant project failure
- "medium" — important consideration that requires mitigation planning
- "low"   — worth noting but manageable with standard practices

CATEGORY DEFINITIONS:
- deadline: tight timelines, short submission windows, aggressive schedules
- compliance: regulatory certifications required (ISO, HIPAA, FedRAMP, CMMC, SOC 2, etc.)
- technical: complex or unusual technical requirements, performance demands, integrations
- pricing: budget appears insufficient, pricing unclear, fixed-price with open scope
- capacity: scope exceeds typical team size; resource-intensive staffing requirements
- eligibility: specific certs/licenses/clearances/set-asides required to be eligible
- documentation: many required attachments, notarizations, complex submission requirements
- scope: vague, expanding, or contradictory scope; unclear or missing deliverables
- competition: signals of incumbent advantage, sole-source language, pre-selected vendor

STRICT RULES:
- Only include risks with DIRECT EVIDENCE from the RFP data provided.
- Do NOT invent risks not supported by the content.
- If no clear risks exist, return {{"risks": []}} — do not force-fit risks.
- If something could be a risk but evidence is weak, set severity to "low" and \
note the uncertainty explicitly in the description field.
- Return at most 8 risks; prioritize those most relevant to the bid/no-bid decision.
- Order by severity descending (high first).

RFP DATA:
{req_text}

Return only valid JSON. No markdown, no explanation outside the JSON."""


# ── Public API ────────────────────────────────────────────────────────────────

def identify_risks(
    requirements: dict | str, industry: Optional[str] = None
) -> list[dict]:
    """
    Identify bid risks from structured RFP extraction output.

    Returns a list of risk objects. Never raises — falls back to heuristics
    if the LLM call fails or the API key is absent.
    """
    from services.industry import get_industry_context
    ctx = get_industry_context(industry)

    req_dict = requirements if isinstance(requirements, dict) else {}
    req_text = json.dumps(requirements, indent=2) if isinstance(requirements, dict) else str(requirements)

    prompt = _RISK_PROMPT.format(
        vendor_type=ctx["vendor_type"],
        req_text=req_text[:5000],
    )

    try:
        logger.debug("LLM call identify_risks model=claude-haiku-4-5-20251001")
        message = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        raw = result.get("risks", [])
        risks = [_normalize(r) for r in raw if _is_valid(r)]
        logger.debug("Risk identification completed risks=%d", len(risks))
        return risks

    except Exception as exc:
        logger.warning(
            "LLM risk identification failed (%s) — falling back to heuristic risks", exc
        )
        return _heuristic_risks(req_dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _is_valid(r: object) -> bool:
    """Risk must be a dict with all required fields and valid enum values."""
    if not isinstance(r, dict):
        return False
    return (
        bool(r.get("title"))
        and bool(r.get("description"))
        and r.get("severity") in VALID_SEVERITIES
        and r.get("category") in VALID_CATEGORIES
        and bool(r.get("evidence"))
    )


def _normalize(r: dict) -> dict:
    """Truncate long strings and coerce any invalid enum values to safe defaults."""
    return {
        "title":       str(r.get("title",       "Unspecified risk"))[:120],
        "description": str(r.get("description", ""))[:500],
        "severity":    r["severity"] if r.get("severity") in VALID_SEVERITIES else "medium",
        "category":    r["category"] if r.get("category") in VALID_CATEGORIES else "scope",
        "evidence":    str(r.get("evidence", ""))[:400],
    }


# ── Heuristic fallback (no LLM) ───────────────────────────────────────────────

def _heuristic_risks(requirements: dict) -> list[dict]:
    """
    Keyword-based risk detection used when the LLM is unavailable.
    Conservative — only flags things with direct evidence in the structured data.
    """
    risks: list[dict] = []

    # ── Deadline risk ─────────────────────────────────────────────────────────
    deadline = requirements.get("deadline")
    if deadline:
        risks.append({
            "title": "Submission deadline identified",
            "description": (
                "An explicit deadline was found. Verify there is adequate time "
                "to prepare a complete and compliant submission."
            ),
            "severity": "medium",
            "category": "deadline",
            "evidence": f"Deadline extracted: {deadline}",
        })

    # ── Missing budget ────────────────────────────────────────────────────────
    if not requirements.get("budget"):
        risks.append({
            "title": "Budget not specified",
            "description": (
                "No budget or price ceiling was found. This makes pricing strategy "
                "difficult and increases the risk of under- or over-bidding."
            ),
            "severity": "medium",
            "category": "pricing",
            "evidence": "No budget or cost field found in extracted RFP data.",
        })

    # ── Ambiguous / incomplete document ──────────────────────────────────────
    status = requirements.get("extraction_status")
    if status in ("ambiguous", "failed"):
        risks.append({
            "title": "Incomplete or ambiguous RFP document",
            "description": (
                "The document appears incomplete or poorly structured. "
                "Vague scope increases the risk of misalignment with evaluators."
            ),
            "severity": "medium",
            "category": "scope",
            "evidence": (
                f"Extraction status: {status}. "
                f"Notes: {requirements.get('notes') or 'No additional details.'}"
            ),
        })

    # ── Compliance / certification requirements ───────────────────────────────
    all_req_text = " ".join(
        (r["text"] if isinstance(r, dict) else str(r)).lower()
        for r in requirements.get("requirements", [])
    )
    compliance_kws = [
        "iso", "hipaa", "fedramp", "cmmc", "soc 2", "clearance",
        "certified", "certification", "license", "accreditation",
    ]
    hits = [kw for kw in compliance_kws if kw in all_req_text]
    if hits:
        risks.append({
            "title": "Compliance or certification requirements detected",
            "description": (
                "One or more requirements reference regulatory standards or certifications. "
                "Verify current eligibility before committing to bid."
            ),
            "severity": "high",
            "category": "compliance",
            "evidence": f"Compliance-related terms detected in requirements: {', '.join(hits[:5])}",
        })

    # ── Many mandatory requirements ───────────────────────────────────────────
    mandatory_count = sum(
        1 for r in requirements.get("requirements", [])
        if isinstance(r, dict) and r.get("category") == "mandatory"
    )
    if mandatory_count >= 10:
        risks.append({
            "title": "High volume of mandatory requirements",
            "description": (
                f"{mandatory_count} mandatory requirements were identified. "
                "A large number of hard requirements increases the risk of non-compliance "
                "and proposal preparation burden."
            ),
            "severity": "medium",
            "category": "capacity",
            "evidence": f"{mandatory_count} requirements classified as mandatory.",
        })

    # Sort by severity (high first)
    order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: order.get(r["severity"], 1))
    return risks
