"""
Company profile management and strategic fit evaluation.

Single source of truth: backend/company_profile.json

The profile is loaded from disk on every evaluation call (cheap JSON read).
When company_name is null or empty the profile is treated as "not configured"
and evaluate_strategic_fit returns status="unknown" — no fake fit signal.

Strategic fit dimensions:
  capability_match   (30%) — RFP requirements vs company capabilities/services
  industry_match     (20%) — RFP domain vs company target industries
  contract_size_fit  (15%) — RFP budget vs company target_contract_size range
  geography_fit      (10%) — RFP delivery location vs company geographies
  certification_fit  (15%) — required certs/compliance vs company certifications
  strategic_alignment(10%) — preferred/excluded project types

When no data exists for a dimension, it scores 50 (neutral/unknown) rather than
penalizing unfairly.
"""
import json
import os
from pathlib import Path
from typing import Optional
import anthropic
from dotenv import load_dotenv
from settings import llm_model

load_dotenv()

PROFILE_PATH = Path(__file__).parent.parent / "company_profile.json"

# Dimension weights (must sum to 1.0)
_DIM_WEIGHTS = {
    "capability_match":    0.30,
    "industry_match":      0.20,
    "contract_size_fit":   0.15,
    "geography_fit":       0.10,
    "certification_fit":   0.15,
    "strategic_alignment": 0.10,
}

_VALID_OVERALL = {"high", "medium", "low"}

_client = None


# ── Profile I/O ───────────────────────────────────────────────────────────────

def load_profile() -> Optional[dict]:
    """
    Load the company profile from disk.
    Returns None if the file doesn't exist or company_name is not set.
    Strips the internal _note field before returning.
    """
    if not PROFILE_PATH.exists():
        return None
    try:
        data = json.loads(PROFILE_PATH.read_text())
    except Exception:
        return None
    data.pop("_note", None)
    if not data.get("company_name"):
        return None
    return data


def save_profile(data: dict) -> dict:
    """Persist the profile to disk. Returns the saved (cleaned) profile."""
    data.pop("_note", None)
    PROFILE_PATH.write_text(json.dumps(data, indent=2))
    return data


def is_configured() -> bool:
    """True only when a profile with a non-empty company_name exists."""
    return load_profile() is not None


# ── Strategic fit evaluation ──────────────────────────────────────────────────

def evaluate_strategic_fit(
    requirements: dict | str,
    profile: Optional[dict],
) -> dict:
    """
    Compare an RFP against the company profile across 6 dimensions.

    Returns:
      - status="unknown"   when profile is None/unconfigured
      - status="evaluated" when fit was computed (LLM or heuristic)
    """
    if not profile:
        return {
            "status": "unknown",
            "reason": (
                "No company profile is configured. "
                "Set up your profile at GET/PUT /api/profile to enable strategic fit evaluation."
            ),
        }

    req_dict = requirements if isinstance(requirements, dict) else {}
    req_text = (
        json.dumps(requirements, indent=2)
        if isinstance(requirements, dict)
        else str(requirements)
    )

    try:
        result = _evaluate_with_llm(req_text, profile)
        return _build_result(result, profile["company_name"])
    except Exception:
        result = _evaluate_heuristic(req_dict, profile)
        return _build_result(result, profile["company_name"])


# ── LLM evaluation ────────────────────────────────────────────────────────────

_FIT_PROMPT = """\
You are a strategic bid advisor. Compare the RFP data against the company profile \
and evaluate strategic fit across 6 dimensions.

COMPANY PROFILE:
{profile_text}

RFP DATA:
{rfp_text}

Return a JSON object with exactly these fields:
{{
  "dimensions": [
    {{
      "name": "capability_match",
      "score": <integer 0-100>,
      "reason": "<one sentence citing specific capabilities from profile vs RFP requirements>"
    }},
    {{
      "name": "industry_match",
      "score": <integer 0-100>,
      "reason": "<one sentence comparing RFP domain to company target industries>"
    }},
    {{
      "name": "contract_size_fit",
      "score": <integer 0-100>,
      "reason": "<one sentence comparing RFP budget to company target_contract_size range>"
    }},
    {{
      "name": "geography_fit",
      "score": <integer 0-100>,
      "reason": "<one sentence on delivery location alignment>"
    }},
    {{
      "name": "certification_fit",
      "score": <integer 0-100>,
      "reason": "<one sentence comparing required certifications to company certifications>"
    }},
    {{
      "name": "strategic_alignment",
      "score": <integer 0-100>,
      "reason": "<one sentence on preferred/excluded project type alignment>"
    }}
  ],
  "summary": "<2 sentences summarizing overall strategic fit>"
}}

SCORING RULES:
- Score 0–100 per dimension; 50 = insufficient data to evaluate (neutral)
- Be specific: reference capability names, certification names, budget figures when present
- If the RFP type appears in excluded_project_types, score strategic_alignment 0–20
- Do NOT invent alignment not evidenced in both profile and RFP data
- If a dimension cannot be evaluated (no relevant data on either side), score it 50

Return only valid JSON. No markdown."""


def _evaluate_with_llm(req_text: str, profile: dict) -> dict:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    profile_text = json.dumps(profile, indent=2)
    prompt = _FIT_PROMPT.format(
        profile_text=profile_text[:2000],
        rfp_text=req_text[:3000],
    )

    message = _client.messages.create(
        model=llm_model,
        max_tokens=1200,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    content = message.content[0].text
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    return json.loads(content)


# ── Heuristic fallback ────────────────────────────────────────────────────────

def _evaluate_heuristic(requirements: dict, profile: dict) -> dict:
    """
    Rule-based fit evaluation used when LLM is unavailable.
    Produces scores with explicit evidence. Scores 50 when data is missing.
    """
    dimensions = []

    # ── capability_match ─────────────────────────────────────────────────────
    rfp_keywords = set(k.lower() for k in requirements.get("keywords", []))
    rfp_req_text = " ".join(
        (r["text"] if isinstance(r, dict) else str(r)).lower()
        for r in requirements.get("requirements", [])
    )
    profile_caps = [c.lower() for c in (profile.get("capabilities") or [])
                    + (profile.get("services") or [])]

    if profile_caps and (rfp_keywords or rfp_req_text):
        matches = [c for c in profile_caps
                   if c in rfp_req_text or any(w in rfp_req_text for w in c.split())]
        ratio = len(matches) / len(profile_caps) if profile_caps else 0
        cap_score = min(100, int(50 + ratio * 60))
        reason = (
            f"Matched {len(matches)}/{len(profile_caps)} capabilities: "
            f"{', '.join(matches[:3]) or 'none'}"
        )
    else:
        cap_score, reason = 50, "Insufficient data to evaluate capability match."
    dimensions.append({"name": "capability_match", "score": cap_score, "reason": reason})

    # ── industry_match ────────────────────────────────────────────────────────
    rfp_summary = (requirements.get("summary") or "").lower()
    profile_industries = [i.lower() for i in (profile.get("industries") or [])]

    if profile_industries:
        hit = any(ind.replace("_", " ") in rfp_summary or ind in rfp_summary
                  for ind in profile_industries)
        ind_score = 85 if hit else 25
        reason = (
            f"RFP domain matches company industry list ({', '.join(profile_industries[:3])})."
            if hit else
            f"RFP domain does not clearly match company industries ({', '.join(profile_industries[:3])})."
        )
    else:
        ind_score, reason = 50, "Company industry list not configured."
    dimensions.append({"name": "industry_match", "score": ind_score, "reason": reason})

    # ── contract_size_fit ─────────────────────────────────────────────────────
    budget_str = (requirements.get("budget") or "").lower()
    size_cfg = profile.get("target_contract_size") or {}
    min_size = size_cfg.get("min")
    max_size = size_cfg.get("max")

    if budget_str and min_size is not None and max_size is not None:
        # Extract first number from budget string
        import re
        nums = re.findall(r"[\d,]+", budget_str.replace(",", ""))
        budget_val = int(nums[0]) if nums else None
        if budget_val is not None:
            if min_size <= budget_val <= max_size:
                sz_score = 90
                reason = f"Budget ~${budget_val:,} is within target range ${min_size:,}–${max_size:,}."
            elif budget_val < min_size:
                sz_score = max(20, int(50 * budget_val / min_size))
                reason = f"Budget ~${budget_val:,} is below minimum target ${min_size:,}."
            else:
                ratio = max_size / budget_val
                sz_score = max(20, int(50 + 40 * ratio))
                reason = f"Budget ~${budget_val:,} exceeds maximum target ${max_size:,}."
        else:
            sz_score, reason = 50, "Budget present but could not be parsed as a number."
    else:
        sz_score = 50
        reason = "Budget or contract size range not available for comparison."
    dimensions.append({"name": "contract_size_fit", "score": sz_score, "reason": reason})

    # ── geography_fit ─────────────────────────────────────────────────────────
    profile_geos = [g.lower() for g in (profile.get("geographies") or [])]
    if profile_geos:
        if "remote" in profile_geos or not rfp_summary:
            geo_score = 80
            reason = "Company supports remote delivery; geography is not a constraint."
        else:
            hit = any(g in rfp_summary for g in profile_geos)
            geo_score = 75 if hit else 40
            reason = (
                f"RFP geography aligns with company operating regions ({', '.join(profile_geos[:3])})."
                if hit else
                "RFP geography does not clearly match company operating regions."
            )
    else:
        geo_score, reason = 50, "Company geographies not configured."
    dimensions.append({"name": "geography_fit", "score": geo_score, "reason": reason})

    # ── certification_fit ─────────────────────────────────────────────────────
    profile_certs = [c.lower() for c in (profile.get("certifications") or [])]
    # Look for compliance requirements in the RFP
    compliance_kws = ["iso", "hipaa", "fedramp", "cmmc", "soc 2", "clearance",
                      "certified", "certification", "license", "accredited"]
    required_certs = [kw for kw in compliance_kws if kw in rfp_req_text]

    if required_certs and profile_certs:
        matched = [c for c in required_certs
                   if any(c in pc or pc in c for pc in profile_certs)]
        ratio = len(matched) / len(required_certs)
        cert_score = min(100, int(40 + ratio * 60))
        reason = (
            f"Company holds {len(matched)}/{len(required_certs)} required cert types "
            f"({', '.join(matched[:3]) or 'none matched'})."
        )
    elif not required_certs:
        cert_score = 80
        reason = "No specific certifications required in the RFP."
    else:
        cert_score = 40
        reason = "RFP requires certifications but company cert list is empty."
    dimensions.append({"name": "certification_fit", "score": cert_score, "reason": reason})

    # ── strategic_alignment ───────────────────────────────────────────────────
    excluded = [e.lower() for e in (profile.get("excluded_project_types") or [])]
    preferred = [p.lower() for p in (profile.get("preferred_project_types") or [])]

    excluded_hit = any(e in rfp_summary or e in rfp_req_text for e in excluded)
    preferred_hit = any(p in rfp_summary or p in rfp_req_text for p in preferred)

    if excluded_hit:
        strat_score = 10
        reason = "RFP type matches an excluded project category for this company."
    elif preferred_hit:
        strat_score = 90
        reason = "RFP matches a preferred project type for this company."
    elif excluded or preferred:
        strat_score = 55
        reason = "RFP type is neutral — not preferred or excluded."
    else:
        strat_score = 50
        reason = "Preferred and excluded project types not configured."
    dimensions.append({"name": "strategic_alignment", "score": strat_score, "reason": reason})

    # ── summary ───────────────────────────────────────────────────────────────
    high = [d["name"] for d in dimensions if d["score"] >= 70]
    low  = [d["name"] for d in dimensions if d["score"] < 40]
    summary = (
        f"Strong alignment in: {', '.join(high)}. " if high else "No strong alignment dimensions. "
    ) + (
        f"Weak alignment in: {', '.join(low)}." if low else "No critically weak dimensions."
    )

    return {"dimensions": dimensions, "summary": summary}


# ── Result builder ────────────────────────────────────────────────────────────

def _build_result(raw: dict, company_name: str) -> dict:
    """
    Take raw LLM or heuristic output and produce the canonical strategic_fit dict.
    Computes weighted overall score and overall label.
    """
    dimensions = raw.get("dimensions", [])

    # Validate and normalize each dimension
    clean_dims = []
    for d in dimensions:
        if not isinstance(d, dict) or "name" not in d:
            continue
        name = d["name"]
        score = d.get("score", 50)
        if not isinstance(score, (int, float)):
            score = 50
        score = max(0, min(100, int(score)))
        clean_dims.append({
            "name": name,
            "score": score,
            "reason": str(d.get("reason", ""))[:300],
        })

    # Weighted average using defined weights; unrecognized dims count as 50
    total_weight = 0.0
    weighted_sum = 0.0
    for d in clean_dims:
        w = _DIM_WEIGHTS.get(d["name"], 0)
        weighted_sum += d["score"] * w
        total_weight += w

    # Fill in any missing dimensions at 50
    for dim_name, w in _DIM_WEIGHTS.items():
        if not any(d["name"] == dim_name for d in clean_dims):
            weighted_sum += 50 * w
            total_weight += w
            clean_dims.append({"name": dim_name, "score": 50,
                                "reason": "Insufficient data to evaluate."})

    overall_score = round(weighted_sum / total_weight) if total_weight else 50
    overall_label = "high" if overall_score >= 66 else ("medium" if overall_score >= 41 else "low")

    return {
        "status": "evaluated",
        "profile_name": company_name,
        "overall": overall_label,
        "score": overall_score,
        "dimensions": clean_dims,
        "summary": str(raw.get("summary", ""))[:400],
    }
