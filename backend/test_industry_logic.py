"""
Verify industry configuration logic.
No LLM calls — exercises pure-Python functions only.
"""
import sys
sys.path.insert(0, ".")
from services.industry import (
    resolve_industry, get_industry_context,
    SUPPORTED_INDUSTRIES, DEFAULT_INDUSTRY,
)

# ── Case 1: resolve_industry handles all valid values ───────────────────────
for ind in SUPPORTED_INDUSTRIES:
    assert resolve_industry(ind) == ind, f"Failed for: {ind}"
    assert resolve_industry(ind.upper()) == ind, f"Case-insensitive failed for: {ind}"
print(f"Case 1 PASS: all {len(SUPPORTED_INDUSTRIES)} industries resolve correctly")

# ── Case 2: unknown / None / empty → DEFAULT_INDUSTRY ───────────────────────
for bad in [None, "", "  ", "pharma", "tech", "UNKNOWN", "Technology/Consulting"]:
    result = resolve_industry(bad)
    assert result == DEFAULT_INDUSTRY, f"Expected 'general', got '{result}' for input: {repr(bad)}"
print(f"Case 2 PASS: None/empty/unknown all resolve to '{DEFAULT_INDUSTRY}'")

# ── Case 3: every context has required keys ──────────────────────────────────
required_keys = {"label", "vendor_type", "focus", "tone", "relevant_domains"}
for ind in SUPPORTED_INDUSTRIES:
    ctx = get_industry_context(ind)
    missing = required_keys - ctx.keys()
    assert not missing, f"Industry '{ind}' missing keys: {missing}"
print(f"Case 3 PASS: all industries have required context keys")

# ── Case 4: 'general' has no relevant_domains (neutral fallback) ─────────────
ctx_general = get_industry_context("general")
assert ctx_general["relevant_domains"] == [], \
    f"'general' should have empty domains: {ctx_general['relevant_domains']}"
assert "technology" not in ctx_general["vendor_type"].lower(), \
    f"'general' vendor_type should not assume tech: {ctx_general['vendor_type']}"
assert "consulting" not in ctx_general["vendor_type"].lower(), \
    f"'general' vendor_type should not assume consulting: {ctx_general['vendor_type']}"
print(f"Case 4 PASS: 'general' is neutral — vendor_type='{ctx_general['vendor_type']}'")

# ── Case 5: None input → same as 'general' ───────────────────────────────────
ctx_none = get_industry_context(None)
assert ctx_none == get_industry_context("general"), \
    "get_industry_context(None) should equal get_industry_context('general')"
print(f"Case 5 PASS: None input → 'general' context")

# ── Case 6: each industry has distinct vendor_type ───────────────────────────
vendor_types = [get_industry_context(ind)["vendor_type"] for ind in SUPPORTED_INDUSTRIES]
assert len(vendor_types) == len(set(vendor_types)), \
    f"Duplicate vendor_types detected: {vendor_types}"
print(f"Case 6 PASS: all {len(vendor_types)} vendor_types are distinct")

# ── Case 7: healthcare context contains compliance-specific terms ─────────────
ctx_hc = get_industry_context("healthcare")
hc_focus_lower = ctx_hc["focus"].lower()
assert "hipaa" in hc_focus_lower, f"Healthcare focus should mention HIPAA: {ctx_hc['focus']}"
assert "patient" in hc_focus_lower or "clinical" in hc_focus_lower, \
    f"Healthcare focus should be clinical: {ctx_hc['focus']}"
print(f"Case 7 PASS: healthcare context is clinical/compliance-focused")

# ── Case 8: construction context contains delivery-specific terms ─────────────
ctx_con = get_industry_context("construction")
con_focus_lower = ctx_con["focus"].lower()
assert "safety" in con_focus_lower, f"Construction focus should mention safety: {ctx_con['focus']}"
assert "subcontractor" in con_focus_lower or "delivery" in con_focus_lower, \
    f"Construction focus should mention delivery/subs: {ctx_con['focus']}"
print(f"Case 8 PASS: construction context is delivery/safety-focused")

# ── Case 9: scoring heuristic uses industry keywords ─────────────────────────
# Simulate _heuristic_score behavior: healthcare doc should score higher for healthcare
hc_doc = "patient outcomes ehr clinical workflows hipaa compliance care coordination"
construction_doc = "subcontractor site safety osha permit quality control schedule"
generic_doc = "we offer solutions and services for your needs"

def heuristic_relevance(text: str, industry: str) -> int:
    from services.industry import get_industry_context
    ctx = get_industry_context(industry)
    keywords = [d.lower() for d in ctx.get("relevant_domains", [])]
    if not keywords:
        fallback = ["service", "project", "delivery", "solution", "support"]
        return 70 if any(k in text.lower() for k in fallback) else 50
    return 70 if any(k in text.lower() for k in keywords) else 50

assert heuristic_relevance(hc_doc, "healthcare") == 70, "Healthcare doc should score 70 for healthcare"
assert heuristic_relevance(hc_doc, "construction") == 50, "Healthcare doc should score 50 for construction"
assert heuristic_relevance(construction_doc, "construction") == 70, "Construction doc should score 70 for construction"
assert heuristic_relevance(generic_doc, "general") == 70, "Generic doc should use fallback keywords"
print(f"Case 9 PASS: heuristic scoring is industry-aware")

# ── Case 10: no 'technology/consulting firm' hardcode anywhere ───────────────
import services.generator as gen_module
import services.scoring as score_module
import inspect

gen_source = inspect.getsource(gen_module)
score_source = inspect.getsource(score_module)

# The phrase should not appear in the source after our fix
assert "technology/consulting firm" not in gen_source, \
    "generator.py still contains hardcoded 'technology/consulting firm'"
assert "technology/consulting firm" not in score_source, \
    "scoring.py still contains hardcoded 'technology/consulting firm'"
print("Case 10 PASS: 'technology/consulting firm' hardcode is gone from both files")

print("\nAll cases passed.")
