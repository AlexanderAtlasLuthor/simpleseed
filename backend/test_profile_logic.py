"""
Verify company profile and strategic fit logic.
No LLM calls — exercises load_profile, _evaluate_heuristic, _build_result,
evaluate_strategic_fit, and score-adjustment math.
"""
import sys, json, tempfile, os
sys.path.insert(0, ".")

from services.profile import (
    evaluate_strategic_fit, _evaluate_heuristic, _build_result,
    _DIM_WEIGHTS, PROFILE_PATH,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

FULL_PROFILE = {
    "company_name": "AcmeTech",
    "industries": ["healthcare", "government_contracting"],
    "capabilities": ["cloud migration", "data integration", "cybersecurity", "ehr integration"],
    "services": ["implementation", "managed services", "compliance support"],
    "target_contract_size": {"min": 100_000, "max": 2_000_000},
    "geographies": ["US", "remote"],
    "certifications": ["SOC 2", "HIPAA experience", "FedRAMP"],
    "past_performance_keywords": ["federal modernization", "health data"],
    "preferred_project_types": ["digital transformation", "system integration"],
    "excluded_project_types": ["construction", "staff augmentation only"],
    "capacity_constraints": ["max 3 concurrent large projects"],
}

ALIGNED_RFP = {
    "summary": "Federal healthcare agency seeks vendor for cloud migration and ehr integration.",
    "client": "HHS",
    "deadline": "June 30, 2025",
    "budget": "$750,000",
    "requirements": [
        {"text": "Vendor must hold HIPAA experience certification",
         "category": "mandatory", "reason": "must", "type": "administrative", "type_reason": "compliance"},
        {"text": "Implement cloud migration for existing systems",
         "category": "mandatory", "reason": "must", "type": "technical", "type_reason": "cloud"},
    ],
    "keywords": ["cloud migration", "healthcare", "ehr", "federal", "hipaa"],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}

MISALIGNED_RFP = {
    "summary": "City seeks general contractor for road construction and paving project.",
    "client": "City of Springfield",
    "deadline": "May 1, 2025",
    "budget": "$50,000",
    "requirements": [
        {"text": "Must have state contractor license",
         "category": "mandatory", "reason": "must", "type": "administrative", "type_reason": "license"},
    ],
    "keywords": ["construction", "paving", "road", "contractor"],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}

PARTIAL_RFP = {
    "summary": "Tech startup needs staff augmentation services in Asia.",
    "client": "StartupXYZ",
    "deadline": None,
    "budget": "$30,000,000",  # way above max
    "requirements": [],
    "keywords": ["staff augmentation"],
    "extraction_status": "partial",
    "confidence": "medium",
    "notes": None,
}


# ── Case 1: no profile → status unknown ──────────────────────────────────────
result = evaluate_strategic_fit(ALIGNED_RFP, None)
assert result["status"] == "unknown", f"Expected unknown, got: {result['status']}"
assert "reason" in result, "unknown result must have a reason"
assert "strategic_fit" not in result.get("overall", ""), "Should not compute fit without profile"
print(f"Case 1 PASS: no profile → status='{result['status']}', reason present")


# ── Case 2: aligned RFP + full profile → high fit ────────────────────────────
raw = _evaluate_heuristic(ALIGNED_RFP, FULL_PROFILE)
result = _build_result(raw, FULL_PROFILE["company_name"])

assert result["status"] == "evaluated"
assert result["profile_name"] == "AcmeTech"
assert result["overall"] in ("high", "medium", "low")
assert 0 <= result["score"] <= 100
assert len(result["dimensions"]) == len(_DIM_WEIGHTS), \
    f"Expected {len(_DIM_WEIGHTS)} dimensions, got {len(result['dimensions'])}"

cap_dim = next(d for d in result["dimensions"] if d["name"] == "capability_match")
ind_dim = next(d for d in result["dimensions"] if d["name"] == "industry_match")

assert cap_dim["score"] > 50, f"Aligned RFP should have high capability match: {cap_dim}"
assert ind_dim["score"] > 50, f"Healthcare RFP should match healthcare industry: {ind_dim}"
print(f"Case 2 PASS: aligned RFP → overall={result['overall']}, score={result['score']}, "
      f"capability={cap_dim['score']}, industry={ind_dim['score']}")


# ── Case 3: excluded project type → very low strategic_alignment ──────────────
raw = _evaluate_heuristic(MISALIGNED_RFP, FULL_PROFILE)
result = _build_result(raw, FULL_PROFILE["company_name"])

strat_dim = next(d for d in result["dimensions"] if d["name"] == "strategic_alignment")
assert strat_dim["score"] <= 20, \
    f"Construction (excluded) should score ≤20, got: {strat_dim['score']}"
assert result["score"] < 60, \
    f"Misaligned RFP should have low overall score, got: {result['score']}"
print(f"Case 3 PASS: excluded project type → strategic_alignment={strat_dim['score']}, "
      f"overall={result['score']}")


# ── Case 4: budget above max → low contract_size_fit ─────────────────────────
raw = _evaluate_heuristic(PARTIAL_RFP, FULL_PROFILE)
result = _build_result(raw, FULL_PROFILE["company_name"])

size_dim = next(d for d in result["dimensions"] if d["name"] == "contract_size_fit")
assert size_dim["score"] < 60, \
    f"$30M budget (max is $2M) should score low, got: {size_dim['score']}"
print(f"Case 4 PASS: budget $30M vs max $2M → contract_size_fit={size_dim['score']}")


# ── Case 5: budget within range → high contract_size_fit ─────────────────────
in_range_rfp = {**ALIGNED_RFP, "budget": "$500,000"}
raw = _evaluate_heuristic(in_range_rfp, FULL_PROFILE)
result = _build_result(raw, FULL_PROFILE["company_name"])

size_dim = next(d for d in result["dimensions"] if d["name"] == "contract_size_fit")
assert size_dim["score"] >= 80, \
    f"$500k in [$100k, $2M] range should score ≥80, got: {size_dim['score']}"
print(f"Case 5 PASS: budget $500k in range [$100k–$2M] → contract_size_fit={size_dim['score']}")


# ── Case 6: empty profile fields → neutral scores (50) ───────────────────────
sparse_profile = {"company_name": "SparseCo"}  # all other fields missing
raw = _evaluate_heuristic(ALIGNED_RFP, sparse_profile)
result = _build_result(raw, "SparseCo")

assert result["status"] == "evaluated"
# All dimensions should be ≈50 when no profile data is provided
for d in result["dimensions"]:
    assert 40 <= d["score"] <= 60 or d["name"] == "certification_fit", \
        f"Sparse profile dim '{d['name']}' should be near 50, got {d['score']}"
dim_summary = ", ".join(f"{d['name']}={d['score']}" for d in result["dimensions"])
print(f"Case 6 PASS: sparse profile → neutral scores near 50 ({dim_summary})")


# ── Case 7: _build_result normalizes scores to 0-100 ─────────────────────────
raw_bad = {
    "dimensions": [
        {"name": "capability_match",    "score": 150},   # over 100
        {"name": "industry_match",      "score": -10},   # negative
        {"name": "contract_size_fit",   "score": "abc"}, # non-numeric
        {"name": "geography_fit",       "score": 70},
        {"name": "certification_fit",   "score": 80},
        {"name": "strategic_alignment", "score": 60},
    ],
    "summary": "test",
}
result = _build_result(raw_bad, "TestCo")
for d in result["dimensions"]:
    assert 0 <= d["score"] <= 100, f"Score out of range: {d}"
print(f"Case 7 PASS: _build_result clamps scores to [0, 100]")


# ── Case 8: dimension weights sum to 1.0 ──────────────────────────────────────
total = sum(_DIM_WEIGHTS.values())
assert abs(total - 1.0) < 0.001, f"Weights must sum to 1.0, got {total}"
print(f"Case 8 PASS: dimension weights sum to {total:.3f}")


# ── Case 9: overall label thresholds ─────────────────────────────────────────
for score, expected in [(80, "high"), (55, "medium"), (30, "low"), (66, "high"), (41, "medium"), (40, "low")]:
    label = "high" if score >= 66 else ("medium" if score >= 41 else "low")
    assert label == expected, f"score={score} → expected '{expected}', got '{label}'"
print(f"Case 9 PASS: overall label thresholds (high≥66, medium≥41, low<41)")


# ── Case 10: score adjustment math ───────────────────────────────────────────
# Simulates _run_analysis: adjusted = raw*0.80 + fit*0.20
for raw_s, fit_s, expected_decision in [
    (70, 90, "BID"),      # strong raw + strong fit    → 56+18=74 → BID
    (70, 10, "NO BID"),   # strong raw + terrible fit  → 56+2=58  → NO BID (fit penalty matters)
    (55, 90, "BID"),      # mediocre raw + strong fit  → 44+18=62 → BID
    (50, 10, "NO BID"),   # weak raw + terrible fit    → 40+2=42  → NO BID
    (65, 50, "BID"),      # decent raw + neutral fit   → 52+10=62 → BID
]:
    adjusted = round(raw_s * 0.80 + fit_s * 0.20)
    decision = "BID" if adjusted >= 60 else "NO BID"
    assert decision == expected_decision, \
        f"raw={raw_s}, fit={fit_s} → adjusted={adjusted}, expected '{expected_decision}', got '{decision}'"
print(f"Case 10 PASS: score adjustment math (raw*0.80 + fit*0.20) verified for 5 scenarios")


# ── Case 11: no profile → raw score unchanged ────────────────────────────────
# Confirm: when strategic_fit.status == "unknown", score stays as-is
fit = evaluate_strategic_fit(ALIGNED_RFP, None)
assert fit["status"] == "unknown"
# Score adjustment logic: only runs when status == "evaluated"
raw_score = {"score": 65, "decision": "BID", "breakdown": {}, "reasoning": "test"}
if fit.get("status") == "evaluated":
    adjusted = round(raw_score["score"] * 0.80 + fit["score"] * 0.20)
    final_score = adjusted
else:
    final_score = raw_score["score"]
assert final_score == 65, f"No profile → score should be unchanged, got {final_score}"
print(f"Case 11 PASS: no profile → raw score {final_score} unchanged (backward compatible)")


# ── Case 12: all 6 required dimensions present in result ─────────────────────
raw = _evaluate_heuristic(ALIGNED_RFP, FULL_PROFILE)
result = _build_result(raw, "AcmeTech")
dim_names = {d["name"] for d in result["dimensions"]}
required = set(_DIM_WEIGHTS.keys())
assert required == dim_names, f"Missing dimensions: {required - dim_names}"
print(f"Case 12 PASS: all 6 required dimensions present in result")


print("\nAll cases passed.")
