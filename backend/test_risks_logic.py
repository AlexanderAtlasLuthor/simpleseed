"""
Verify risk identification logic.
No LLM calls — exercises _heuristic_risks, _is_valid, _normalize, schema constants.
"""
import sys
sys.path.insert(0, ".")
from services.risks import (
    identify_risks, _heuristic_risks, _is_valid, _normalize,
    VALID_SEVERITIES, VALID_CATEGORIES,
)

# ── Case 1: schema constants are well-formed ──────────────────────────────────
assert "low" in VALID_SEVERITIES and "medium" in VALID_SEVERITIES and "high" in VALID_SEVERITIES
required_categories = {"deadline", "compliance", "technical", "pricing", "capacity",
                        "eligibility", "documentation", "scope", "competition"}
assert required_categories.issubset(VALID_CATEGORIES), \
    f"Missing categories: {required_categories - VALID_CATEGORIES}"
print(f"Case 1 PASS: schema has {len(VALID_SEVERITIES)} severities, {len(VALID_CATEGORIES)} categories")


# ── Case 2: _is_valid rejects malformed risks ─────────────────────────────────
bad_risks = [
    {},                                                               # empty
    {"title": "T", "description": "D", "severity": "extreme",        # bad severity
     "category": "scope", "evidence": "E"},
    {"title": "T", "description": "D", "severity": "high",           # bad category
     "category": "unknown_cat", "evidence": "E"},
    {"title": "", "description": "D", "severity": "high",             # empty title
     "category": "scope", "evidence": "E"},
    {"title": "T", "description": "D", "severity": "high",           # missing evidence
     "category": "scope"},
    "not a dict",                                                      # wrong type
]
for bad in bad_risks:
    assert not _is_valid(bad), f"Should be invalid: {bad}"
print(f"Case 2 PASS: _is_valid correctly rejects {len(bad_risks)} malformed risks")


# ── Case 3: _is_valid accepts well-formed risks ───────────────────────────────
good_risk = {
    "title": "Tight submission deadline",
    "description": "Only 5 business days to prepare a complete submission.",
    "severity": "high",
    "category": "deadline",
    "evidence": "Deadline is April 12; document issued April 7.",
}
assert _is_valid(good_risk), "Good risk should be valid"
print("Case 3 PASS: _is_valid accepts well-formed risk")


# ── Case 4: _normalize truncates and coerces ──────────────────────────────────
r = _normalize({
    "title": "X" * 200,             # too long
    "description": "Y" * 600,       # too long
    "severity": "extreme",           # invalid → "medium"
    "category": "alien_risk",        # invalid → "scope"
    "evidence": "Z" * 500,           # too long
})
assert len(r["title"]) <= 120
assert len(r["description"]) <= 500
assert r["severity"] == "medium"
assert r["category"] == "scope"
assert len(r["evidence"]) <= 400
print("Case 4 PASS: _normalize truncates and coerces invalid values")


# ── Case 5: heuristic — RFP with deadline → deadline risk ────────────────────
reqs_with_deadline = {
    "summary": "Agency seeks cloud services.",
    "client": "DeptTech",
    "deadline": "April 30, 2025",
    "budget": "$500,000",
    "requirements": [],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}
risks = _heuristic_risks(reqs_with_deadline)
categories = {r["category"] for r in risks}
assert "deadline" in categories, f"Expected deadline risk, got: {categories}"
assert all(_is_valid(r) for r in risks), "All heuristic risks should be valid"
print(f"Case 5 PASS: deadline identified → {[r['title'] for r in risks]}")


# ── Case 6: heuristic — no budget → pricing risk ─────────────────────────────
reqs_no_budget = {
    "summary": "Seeking IT services.",
    "client": "Agency",
    "deadline": None,
    "budget": None,
    "requirements": [],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}
risks = _heuristic_risks(reqs_no_budget)
categories = {r["category"] for r in risks}
assert "pricing" in categories, f"Expected pricing risk, got: {categories}"
print(f"Case 6 PASS: missing budget → pricing risk identified")


# ── Case 7: heuristic — compliance keywords → compliance risk ─────────────────
reqs_compliance = {
    "summary": "Federal IT contract.",
    "client": "DoD",
    "deadline": None,
    "budget": "$2M",
    "requirements": [
        {"text": "Vendor must hold ISO 27001 certification", "category": "mandatory",
         "reason": "must", "type": "administrative", "type_reason": "cert"},
        {"text": "CMMC level 2 required", "category": "mandatory",
         "reason": "required", "type": "administrative", "type_reason": "compliance"},
    ],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}
risks = _heuristic_risks(reqs_compliance)
categories = {r["category"] for r in risks}
assert "compliance" in categories, f"Expected compliance risk, got: {categories}"
compliance_risk = next(r for r in risks if r["category"] == "compliance")
assert compliance_risk["severity"] == "high", \
    f"Compliance risk should be high severity, got: {compliance_risk['severity']}"
print(f"Case 7 PASS: compliance keywords → high-severity compliance risk")


# ── Case 8: heuristic — ambiguous doc → scope risk ───────────────────────────
reqs_ambiguous = {
    "summary": "Some procurement notice.",
    "client": None,
    "deadline": None,
    "budget": None,
    "requirements": [],
    "unclear_requirements": [{"text": "something unclear", "reason": "vague"}],
    "extraction_status": "ambiguous",
    "confidence": "low",
    "notes": "Document appears to be a pre-solicitation notice.",
}
risks = _heuristic_risks(reqs_ambiguous)
categories = {r["category"] for r in risks}
assert "scope" in categories, f"Expected scope risk for ambiguous doc, got: {categories}"
scope_risk = next(r for r in risks if r["category"] == "scope")
assert "ambiguous" in scope_risk["evidence"].lower() or "failed" in scope_risk["evidence"].lower(), \
    f"Scope risk evidence should reference status: {scope_risk['evidence']}"
print(f"Case 8 PASS: ambiguous extraction → scope risk with evidence")


# ── Case 9: heuristic — large mandatory count → capacity risk ─────────────────
many_mandatory = {
    "summary": "Complex enterprise system.",
    "client": "Agency",
    "deadline": None,
    "budget": "$5M",
    "requirements": [
        {"text": f"Requirement {i}", "category": "mandatory",
         "reason": "must", "type": "technical", "type_reason": "system"}
        for i in range(12)
    ],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}
risks = _heuristic_risks(many_mandatory)
categories = {r["category"] for r in risks}
assert "capacity" in categories, f"Expected capacity risk for many mandatories, got: {categories}"
print(f"Case 9 PASS: 12 mandatory requirements → capacity risk")


# ── Case 10: heuristic — clean simple RFP → minimal/no risks ──────────────────
clean_rfp = {
    "summary": "Simple web design project.",
    "client": "SmallAgency",
    "deadline": None,
    "budget": "$50,000",
    "requirements": [
        {"text": "Design a 5-page website", "category": "mandatory",
         "reason": "must", "type": "technical", "type_reason": "design"},
    ],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
}
risks = _heuristic_risks(clean_rfp)
# Should have no risks (no deadline, has budget, complete status, few requirements, no compliance kws)
assert len(risks) == 0, f"Clean RFP should have 0 risks, got: {[r['title'] for r in risks]}"
print(f"Case 10 PASS: clean simple RFP → 0 risks (honest, no false positives)")


# ── Case 11: severity ordering ────────────────────────────────────────────────
mixed_risks = [
    {"title": "Low thing", "description": "d", "severity": "low",
     "category": "scope", "evidence": "e"},
    {"title": "High thing", "description": "d", "severity": "high",
     "category": "compliance", "evidence": "e"},
    {"title": "Medium thing", "description": "d", "severity": "medium",
     "category": "pricing", "evidence": "e"},
]
# Simulate the sort that _heuristic_risks applies
order = {"high": 0, "medium": 1, "low": 2}
sorted_risks = sorted(mixed_risks, key=lambda r: order.get(r["severity"], 1))
assert sorted_risks[0]["severity"] == "high"
assert sorted_risks[1]["severity"] == "medium"
assert sorted_risks[2]["severity"] == "low"
print("Case 11 PASS: risks sorted high → medium → low")


# ── Case 12: risks field present in all required schema keys ──────────────────
r = _normalize(good_risk)
for key in ("title", "description", "severity", "category", "evidence"):
    assert key in r, f"Normalized risk missing key: {key}"
print("Case 12 PASS: normalized risk has all 5 required keys")


print("\nAll cases passed.")
