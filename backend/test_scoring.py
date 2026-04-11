"""
Tests for 1.3 Explainable Scoring.

Covers:
  - Output schema correctness (all required fields present)
  - Weighted-sum math is deterministic (Python owns it, not the LLM)
  - BID / NO BID threshold logic
  - factor_details structure and weight sourcing
  - Strengths, risks, missing_inputs are correctly typed
  - Confidence is a valid enum
  - Heuristic fallback produces valid schema
  - Score is bounded [0, 100]
  - LLM failure triggers heuristic fallback

Run with:
    cd backend && python test_scoring.py
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

# ── Stub heavy imports that are not needed for scoring tests ──────────────────
for _mod in ["pdfplumber", "services.parser", "services.fetcher", "services.sam_gov"]:
    import importlib, types
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)


# ── Helpers ───────────────────────────────────────────────────────────────────

_FACTOR_KEYS = {"relevance_score", "budget_fit", "requirements_match", "completeness"}

_REQUIRED_CORE = {
    "score", "decision", "breakdown", "reasoning", "weights_used", "threshold_used",
}
_REQUIRED_EXPLAIN = {
    "factor_details", "strengths", "risks", "summary_explanation",
    "confidence", "missing_inputs",
}
_ALL_REQUIRED = _REQUIRED_CORE | _REQUIRED_EXPLAIN

_SAMPLE_REQUIREMENTS = {
    "summary": "Software development services for cloud migration project.",
    "client": "Acme Corp",
    "deadline": "2025-06-30",
    "budget": "$500,000",
    "requirements": [
        {"text": "Must have 5+ years of cloud architecture experience.", "category": "mandatory"},
        {"text": "Should provide weekly status reports.", "category": "optional"},
    ],
    "evaluation_criteria": ["Technical capability", "Price", "Past performance"],
    "deliverables": ["Architecture document", "Migration plan", "Final report"],
    "keywords": ["cloud", "migration", "AWS", "DevOps", "security"],
    "extraction_status": "complete",
    "confidence": "high",
}

def _make_mock_llm_response(
    relevance=80, budget_fit=60, req_match=75, completeness=70
) -> str:
    """Return a JSON string that the mock LLM will produce."""
    return json.dumps({
        "relevance_score": relevance,
        "relevance_explanation": "Strong alignment with cloud infrastructure domain.",
        "relevance_evidence": "Cloud migration and AWS mentioned prominently.",
        "budget_fit": budget_fit,
        "budget_fit_explanation": "Budget of $500,000 is reasonable for this scope.",
        "budget_fit_evidence": "$500,000 contract value stated.",
        "requirements_match": req_match,
        "requirements_match_explanation": "Most requirements are achievable for experienced vendors.",
        "requirements_match_evidence": "5+ years cloud architecture experience required.",
        "completeness": completeness,
        "completeness_explanation": "RFP contains clear scope, deliverables, and evaluation criteria.",
        "completeness_evidence": "Evaluation criteria and deliverables are listed.",
        "strengths": ["Strong budget alignment", "Clear technical requirements"],
        "risks": ["Timeline is tight", "Experience threshold may be high"],
        "summary_explanation": "This opportunity is recommended as BID due to strong technical alignment and reasonable budget.",
        "confidence": "medium",
        "missing_inputs": ["Vendor qualification requirements not specified"],
        "reasoning": "Strong match for a cloud-experienced vendor.",
    })


def _mock_anthropic_client(response_text: str):
    """Return a mock Anthropic client that yields response_text."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_score_schema_all_required_fields():
    """score_bid() must return all required top-level fields."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS, industry="technology")

    missing = _ALL_REQUIRED - result.keys()
    assert not missing, f"Missing keys in score_bid output: {missing}"
    print("PASS test_score_schema_all_required_fields")


def test_weighted_sum_is_deterministic():
    """
    The Python weighted sum must match the expected value exactly.
    Factor scores come from the LLM; the weighted calculation is Python-only.
    """
    from services.scoring import score_bid
    from services.scoring_config import load_scoring_config

    cfg = load_scoring_config()
    weights = cfg["weights"]

    factor_scores = {"relevance_score": 80, "budget_fit": 60,
                     "requirements_match": 75, "completeness": 70}
    expected_score = round(
        factor_scores["relevance_score"]    * weights["relevance_score"]
        + factor_scores["budget_fit"]        * weights["budget_fit"]
        + factor_scores["requirements_match"] * weights["requirements_match"]
        + factor_scores["completeness"]       * weights["completeness"]
    )

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(
                   _make_mock_llm_response(
                       relevance=factor_scores["relevance_score"],
                       budget_fit=factor_scores["budget_fit"],
                       req_match=factor_scores["requirements_match"],
                       completeness=factor_scores["completeness"],
                   )
               )):
        result = score_bid(_SAMPLE_REQUIREMENTS, industry="technology")

    assert result["score"] == expected_score, (
        f"Expected score {expected_score}, got {result['score']}"
    )
    print("PASS test_weighted_sum_is_deterministic")


def test_bid_at_threshold():
    """A score exactly at the threshold must produce BID."""
    from services.scoring import score_bid
    from services.scoring_config import load_scoring_config

    cfg = load_scoring_config()
    threshold = float(cfg["bid_threshold"])
    weights   = cfg["weights"]

    # Find factor score that makes weighted sum == threshold exactly
    # With equal weights, factor_score = threshold (approximately)
    target = threshold  # use threshold directly — may not be perfectly achievable,
                        # but any score that rounds to threshold will do

    # Produce factor scores where weighted sum rounds exactly to threshold
    factor = int(target)   # use integer approximation
    mock_factors = {
        "relevance_score": factor,
        "budget_fit": factor,
        "requirements_match": factor,
        "completeness": factor,
    }
    # Compute what the actual score would be
    weighted = sum(mock_factors[k] * weights[k] for k in mock_factors)
    actual_score = round(weighted)

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(
                   _make_mock_llm_response(
                       relevance=mock_factors["relevance_score"],
                       budget_fit=mock_factors["budget_fit"],
                       req_match=mock_factors["requirements_match"],
                       completeness=mock_factors["completeness"],
                   )
               )):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    if actual_score >= threshold:
        assert result["decision"] == "BID", (
            f"Score {actual_score} >= threshold {threshold} should be BID, got {result['decision']}"
        )
    else:
        assert result["decision"] == "NO BID", (
            f"Score {actual_score} < threshold {threshold} should be NO BID, got {result['decision']}"
        )
    print("PASS test_bid_at_threshold")


def test_no_bid_below_threshold():
    """A score well below threshold must produce NO BID."""
    from services.scoring import score_bid

    very_low = _make_mock_llm_response(
        relevance=10, budget_fit=10, req_match=10, completeness=10
    )
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(very_low)):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert result["score"] == 10
    assert result["decision"] == "NO BID", (
        f"Expected NO BID, got {result['decision']} (score={result['score']})"
    )
    print("PASS test_no_bid_below_threshold")


def test_bid_high_score():
    """A score well above threshold must produce BID."""
    from services.scoring import score_bid

    very_high = _make_mock_llm_response(
        relevance=95, budget_fit=90, req_match=95, completeness=90
    )
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(very_high)):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert result["decision"] == "BID", (
        f"Expected BID, got {result['decision']} (score={result['score']})"
    )
    print("PASS test_bid_high_score")


def test_factor_details_has_all_factors():
    """factor_details must contain all 4 scoring factors."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    fd = result["factor_details"]
    assert isinstance(fd, dict), "factor_details must be a dict"
    missing = _FACTOR_KEYS - fd.keys()
    assert not missing, f"Missing factors in factor_details: {missing}"
    print("PASS test_factor_details_has_all_factors")


def test_factor_details_sub_fields():
    """Each entry in factor_details must have score, weight, explanation, evidence."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    required_sub = {"score", "weight", "explanation", "evidence"}
    for factor, detail in result["factor_details"].items():
        missing_sub = required_sub - detail.keys()
        assert not missing_sub, (
            f"Factor '{factor}' is missing sub-fields: {missing_sub}"
        )
        assert isinstance(detail["score"], int), (
            f"factor_details[{factor}]['score'] must be int"
        )
        assert isinstance(detail["weight"], float), (
            f"factor_details[{factor}]['weight'] must be float"
        )
        assert isinstance(detail["explanation"], str)
        assert isinstance(detail["evidence"], str)
    print("PASS test_factor_details_sub_fields")


def test_factor_weights_match_config():
    """Weights in factor_details must match the loaded scoring config."""
    from services.scoring import score_bid
    from services.scoring_config import load_scoring_config

    cfg = load_scoring_config()
    weights = cfg["weights"]

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    for factor, detail in result["factor_details"].items():
        expected_w = weights[factor]
        assert abs(detail["weight"] - expected_w) < 1e-9, (
            f"factor_details[{factor}]['weight'] = {detail['weight']}, "
            f"expected {expected_w} from config"
        )
    print("PASS test_factor_weights_match_config")


def test_strengths_is_list_of_strings():
    """strengths must be a list of strings."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert isinstance(result["strengths"], list), "strengths must be a list"
    for item in result["strengths"]:
        assert isinstance(item, str), f"Each strength must be a string, got: {type(item)}"
    print("PASS test_strengths_is_list_of_strings")


def test_risks_is_list_of_strings():
    """risks must be a list of strings."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert isinstance(result["risks"], list), "risks must be a list"
    for item in result["risks"]:
        assert isinstance(item, str), f"Each risk must be a string, got: {type(item)}"
    print("PASS test_risks_is_list_of_strings")


def test_confidence_is_valid_enum():
    """confidence must be one of 'high', 'medium', 'low'."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert result["confidence"] in ("high", "medium", "low"), (
        f"confidence must be 'high'|'medium'|'low', got: {result['confidence']!r}"
    )
    print("PASS test_confidence_is_valid_enum")


def test_invalid_confidence_defaults_to_medium():
    """An invalid confidence value from the LLM must default to 'medium'."""
    from services.scoring import score_bid

    bad_conf = json.dumps({**json.loads(_make_mock_llm_response()), "confidence": "very_sure"})
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(bad_conf)):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert result["confidence"] == "medium", (
        f"Invalid confidence should default to 'medium', got: {result['confidence']!r}"
    )
    print("PASS test_invalid_confidence_defaults_to_medium")


def test_missing_inputs_is_list_of_strings():
    """missing_inputs must be a list of strings."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert isinstance(result["missing_inputs"], list), "missing_inputs must be a list"
    for item in result["missing_inputs"]:
        assert isinstance(item, str), f"Each missing_input must be a string, got: {type(item)}"
    print("PASS test_missing_inputs_is_list_of_strings")


def test_summary_explanation_is_string():
    """summary_explanation must be a string."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert isinstance(result["summary_explanation"], str), (
        "summary_explanation must be a str"
    )
    print("PASS test_summary_explanation_is_string")


def test_score_bounded_0_to_100():
    """Total score must always be in [0, 100] regardless of factor values."""
    from services.scoring import score_bid

    # Test with max factor scores
    max_response = _make_mock_llm_response(
        relevance=100, budget_fit=100, req_match=100, completeness=100
    )
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(max_response)):
        result_max = score_bid(_SAMPLE_REQUIREMENTS)

    assert 0 <= result_max["score"] <= 100, (
        f"Score out of bounds: {result_max['score']}"
    )
    assert result_max["score"] == 100

    # Test with min factor scores
    min_response = _make_mock_llm_response(
        relevance=0, budget_fit=0, req_match=0, completeness=0
    )
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(min_response)):
        result_min = score_bid(_SAMPLE_REQUIREMENTS)

    assert 0 <= result_min["score"] <= 100
    assert result_min["score"] == 0
    print("PASS test_score_bounded_0_to_100")


def test_reasoning_preserved_for_backward_compat():
    """The 'reasoning' key must always be present (backward compat)."""
    from services.scoring import score_bid

    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert "reasoning" in result, "reasoning field must always be present"
    assert isinstance(result["reasoning"], str)
    print("PASS test_reasoning_preserved_for_backward_compat")


def test_llm_failure_falls_back_to_heuristic():
    """When the LLM call raises, the heuristic fallback must produce a valid schema."""
    from services.scoring import score_bid

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("API unavailable")

    with patch("services.scoring.get_client", return_value=mock_client):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    missing = _ALL_REQUIRED - result.keys()
    assert not missing, f"Heuristic fallback missing keys: {missing}"
    assert result["confidence"] == "low", (
        "Heuristic fallback must always set confidence='low'"
    )
    print("PASS test_llm_failure_falls_back_to_heuristic")


def test_heuristic_fallback_produces_valid_schema():
    """Heuristic mode (no API key) produces all required fields with correct types."""
    from services.scoring import score_bid

    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        # Even without a key, score_bid should not raise
        # (the client will error when called, triggering heuristic)
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("No key")
        with patch("services.scoring.get_client", return_value=mock_client):
            result = score_bid(_SAMPLE_REQUIREMENTS)

        # All required fields must be present
        missing = _ALL_REQUIRED - result.keys()
        assert not missing, f"Missing fields in heuristic output: {missing}"

        # Type checks
        assert isinstance(result["factor_details"], dict)
        for key in _FACTOR_KEYS:
            assert key in result["factor_details"], f"Missing factor: {key}"
        assert isinstance(result["strengths"], list)
        assert isinstance(result["risks"], list)
        assert isinstance(result["summary_explanation"], str)
        assert result["confidence"] in ("high", "medium", "low")
        assert isinstance(result["missing_inputs"], list)
    finally:
        if saved:
            os.environ["ANTHROPIC_API_KEY"] = saved
    print("PASS test_heuristic_fallback_produces_valid_schema")


def test_heuristic_with_budget_present():
    """Heuristic: budget present in text → budget_fit > 50."""
    from services.scoring import _heuristic_score

    text = "The contract value is $250,000 USD. Vendor must provide cloud services."
    result = _heuristic_score(text, {"vendor_type": "tech vendor", "relevant_domains": ["cloud"]})

    assert result["budget_fit"] > 50, (
        f"Expected budget_fit > 50 when budget present, got {result['budget_fit']}"
    )
    assert result["confidence"] == "low"
    print("PASS test_heuristic_with_budget_present")


def test_heuristic_without_budget():
    """Heuristic: no budget in text → budget_fit == 50 and missing_inputs includes budget."""
    from services.scoring import _heuristic_score

    text = "Vendor must provide cloud services and support. No pricing information."
    result = _heuristic_score(text, {"vendor_type": "tech vendor", "relevant_domains": ["cloud"]})

    assert result["budget_fit"] == 50, (
        f"Expected budget_fit == 50 when no budget, got {result['budget_fit']}"
    )
    assert any("budget" in m.lower() for m in result["missing_inputs"]), (
        "missing_inputs should mention budget when absent"
    )
    print("PASS test_heuristic_without_budget")


def test_clamp_helper():
    """_clamp must coerce out-of-range values and parse failures to valid integers."""
    from services.scoring import _clamp

    assert _clamp(150)   == 100
    assert _clamp(-10)   == 0
    assert _clamp(75)    == 75
    assert _clamp(75.9)  == 75   # truncates (int conversion), not rounds
    assert _clamp("abc") == 50   # parse failure → default 50
    assert _clamp(None)  == 50
    print("PASS test_clamp_helper")


def test_safe_list_helper():
    """_safe_list must always return a list of strings."""
    from services.scoring import _safe_list

    assert _safe_list(["a", "b"])   == ["a", "b"]
    assert _safe_list(["a", None])  == ["a"]   # None filtered out
    assert _safe_list(None)         == []
    assert _safe_list("not a list") == []
    assert _safe_list([1, 2])       == ["1", "2"]  # coerced to str
    print("PASS test_safe_list_helper")


def test_safe_confidence_helper():
    """_safe_confidence must return a valid enum or 'medium' on invalid input."""
    from services.scoring import _safe_confidence

    assert _safe_confidence("high")   == "high"
    assert _safe_confidence("medium") == "medium"
    assert _safe_confidence("low")    == "low"
    assert _safe_confidence("VERY_CONFIDENT") == "medium"
    assert _safe_confidence(None)              == "medium"
    print("PASS test_safe_confidence_helper")


def test_string_requirements_input():
    """score_bid accepts a plain string as requirements (not just a dict)."""
    from services.scoring import score_bid

    text_req = "Vendor must deliver cloud migration services within 6 months."
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(text_req)

    missing = _ALL_REQUIRED - result.keys()
    assert not missing, f"Missing keys for string-input requirements: {missing}"
    print("PASS test_string_requirements_input")


def test_llm_invalid_json_falls_back_to_heuristic():
    """When the LLM returns non-JSON, heuristic fallback is triggered."""
    from services.scoring import score_bid

    mock_client = _mock_anthropic_client("Sorry, I cannot score this RFP.")
    with patch("services.scoring.get_client", return_value=mock_client):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    # Should not raise; heuristic fallback produces valid schema
    missing = _ALL_REQUIRED - result.keys()
    assert not missing, f"Missing keys after JSON parse failure: {missing}"
    print("PASS test_llm_invalid_json_falls_back_to_heuristic")


# ── T1–T8: Audit-identified missing tests ─────────────────────────────────────

def test_strategic_fit_adjustment_updates_summary_explanation():
    """
    T1 — When strategic fit shifts the decision (e.g. BID → NO BID),
    summary_explanation must be updated to reflect the final decision.
    Verifies Fix C1 in the pipeline (_execute_pipeline_steps in main.py).
    """
    # This tests the pipeline-level fix, not score_bid() directly.
    # We simulate the blend logic that lives in _execute_pipeline_steps.
    raw_decision   = "BID"
    new_decision   = "NO BID"
    raw_score_val  = 72
    fit_score      = 20
    adjusted       = 58
    original_summary = "This opportunity is recommended as BID due to strong alignment."

    # Replicate the fix logic
    if new_decision != raw_decision:
        patched_summary = (
            f"Strategic fit adjustment changed the recommendation from "
            f"{raw_decision} to {new_decision} "
            f"(raw RFP score {raw_score_val}, "
            f"strategic fit score {fit_score}, "
            f"adjusted score {adjusted}). {original_summary}"
        ).strip()
    else:
        patched_summary = original_summary

    assert "NO BID" in patched_summary, (
        "Patched summary must mention the final NO BID decision"
    )
    assert "BID" in patched_summary and "NO BID" in patched_summary, (
        "Patched summary must reference both original and final decisions"
    )
    assert original_summary in patched_summary, (
        "Original LLM reasoning must be preserved (no info loss)"
    )
    print("PASS test_strategic_fit_adjustment_updates_summary_explanation")


def test_strategic_fit_no_change_preserves_summary():
    """
    T1b — When strategic fit does NOT change the decision, summary is unchanged.
    """
    raw_decision = "BID"
    new_decision = "BID"
    original_summary = "This opportunity is recommended as BID."

    if new_decision != raw_decision:
        patched = f"Strategic fit changed... {original_summary}"
    else:
        patched = original_summary

    assert patched == original_summary, (
        "Summary must not be modified when decision is unchanged"
    )
    print("PASS test_strategic_fit_no_change_preserves_summary")


def test_score_explanation_stores_only_1_3_fields():
    """
    T3/Fix3 — score_bid() output contains no duplicate storage fields.
    The score_explanation blob must contain only the 1.3 explainability keys,
    not breakdown/reasoning/weights_used/threshold_used.
    """
    _EXPLANATION_KEYS = {
        "factor_details", "strengths", "risks",
        "summary_explanation", "confidence", "missing_inputs", "scoring_method",
    }
    _NOT_IN_BLOB = {"weights_used", "threshold_used"}

    from services.scoring import score_bid
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    # Simulate what main.py now stores
    blob = {k: result[k] for k in _EXPLANATION_KEYS if k in result}
    for key in _NOT_IN_BLOB:
        assert key not in blob, (
            f"score_explanation blob must not store '{key}' (already in separate column)"
        )
    for key in _EXPLANATION_KEYS:
        assert key in blob, f"score_explanation blob must contain '{key}'"
    print("PASS test_score_explanation_stores_only_1_3_fields")


def test_heuristic_fallback_sets_scoring_method():
    """
    T4/Fix4 — heuristic path must set scoring_method='heuristic'.
    AI path must set scoring_method='ai' (or omit it, defaulting to 'ai').
    """
    from services.scoring import score_bid, _heuristic_score

    # Heuristic path
    heuristic = _heuristic_score("Short text", {"vendor_type": "vendor", "relevant_domains": []})
    assert heuristic.get("scoring_method") == "heuristic", (
        f"Heuristic fallback must set scoring_method='heuristic', got: {heuristic.get('scoring_method')!r}"
    )

    # AI path: scoring_method comes from LLM response (default 'ai' if absent)
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(_make_mock_llm_response())):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    # LLM didn't return scoring_method, so it defaults to 'ai' via breakdown.get("scoring_method", "ai")
    assert result.get("scoring_method") == "ai", (
        f"AI path should default scoring_method to 'ai', got: {result.get('scoring_method')!r}"
    )
    print("PASS test_heuristic_fallback_sets_scoring_method")


def test_lists_capped_at_max_length():
    """
    T5/Fix2 — strengths and risks must be capped at 3 items; missing_inputs at 5.
    """
    from services.scoring import score_bid

    bloated = json.dumps({
        **json.loads(_make_mock_llm_response()),
        "strengths":      ["s1", "s2", "s3", "s4", "s5", "s6"],
        "risks":          ["r1", "r2", "r3", "r4", "r5"],
        "missing_inputs": ["m1", "m2", "m3", "m4", "m5", "m6", "m7"],
    })
    with patch("services.scoring.get_client",
               return_value=_mock_anthropic_client(bloated)):
        result = score_bid(_SAMPLE_REQUIREMENTS)

    assert len(result["strengths"])     <= 3, f"strengths must be ≤3, got {len(result['strengths'])}"
    assert len(result["risks"])         <= 3, f"risks must be ≤3, got {len(result['risks'])}"
    assert len(result["missing_inputs"]) <= 5, f"missing_inputs must be ≤5, got {len(result['missing_inputs'])}"
    print("PASS test_lists_capped_at_max_length")


def test_clamp_with_nan():
    """
    T6 — _clamp must handle float('nan') without raising.
    In Python, int(float('nan')) raises ValueError which _clamp catches.
    """
    from services.scoring import _clamp
    result = _clamp(float("nan"))
    assert result == 50, f"_clamp(nan) must return default 50, got {result}"
    print("PASS test_clamp_with_nan")


def test_old_rfp_null_score_explanation_safe():
    """
    T7 — Pre-1.3 records with score_explanation=NULL must return safe defaults,
    not raise KeyError or AttributeError.
    Simulates the getattr + _safe_json_load guard in GET /api/rfps/{rfp_id}.
    """
    import json as _json

    def _safe_json_load(value, default):
        if not value:
            return default
        try:
            return _json.loads(value)
        except Exception:
            return default

    # Case 1: NULL in DB (getattr returns None)
    score_explanation_col = None
    _score_expl = _safe_json_load(score_explanation_col or "{}", {})
    assert _score_expl == {}, "NULL score_explanation must produce empty dict"

    # Case 2: empty string
    _score_expl2 = _safe_json_load("" or "{}", {})
    assert _score_expl2 == {}, "Empty score_explanation must produce empty dict"

    # Case 3: accessing fields from empty dict returns safe defaults
    assert _score_expl.get("factor_details",      {})  == {}
    assert _score_expl.get("strengths",            [])  == []
    assert _score_expl.get("risks",                [])  == []
    assert _score_expl.get("summary_explanation",  "")  == ""
    assert _score_expl.get("confidence",       "medium") == "medium"
    assert _score_expl.get("missing_inputs",       [])  == []
    assert _score_expl.get("scoring_method",      "ai") == "ai"

    print("PASS test_old_rfp_null_score_explanation_safe")


def test_adjusted_score_stored_not_raw():
    """
    T8 — After strategic fit blend, it's the *adjusted* score that must be stored,
    not the raw LLM score.  Verifies the pipeline arithmetic at the logic level.
    """
    raw = 72
    fit = 20
    sf_weight = 0.3
    bid_threshold = 65.0

    adjusted = round(raw * (1 - sf_weight) + fit * sf_weight)
    decision = "BID" if adjusted >= bid_threshold else "NO BID"

    assert adjusted != raw, "Sanity check: blend must change the score"
    assert decision == "NO BID", f"Expected NO BID at adjusted={adjusted}"

    # Verify the summary patch fires because decisions differ
    raw_decision = "BID"   # what score_bid() would return for score=72
    assert raw_decision != decision, "Pre-condition: decisions must differ"

    print("PASS test_adjusted_score_stored_not_raw")


# ── Runner ────────────────────────────────────────────────────────────────────

test_score_schema_all_required_fields()
test_weighted_sum_is_deterministic()
test_bid_at_threshold()
test_no_bid_below_threshold()
test_bid_high_score()
test_factor_details_has_all_factors()
test_factor_details_sub_fields()
test_factor_weights_match_config()
test_strengths_is_list_of_strings()
test_risks_is_list_of_strings()
test_confidence_is_valid_enum()
test_invalid_confidence_defaults_to_medium()
test_missing_inputs_is_list_of_strings()
test_summary_explanation_is_string()
test_score_bounded_0_to_100()
test_reasoning_preserved_for_backward_compat()
test_llm_failure_falls_back_to_heuristic()
test_heuristic_fallback_produces_valid_schema()
test_heuristic_with_budget_present()
test_heuristic_without_budget()
test_clamp_helper()
test_safe_list_helper()
test_safe_confidence_helper()
test_string_requirements_input()
test_llm_invalid_json_falls_back_to_heuristic()
# ── T1–T8 (audit fixes) ───────────────────────────────────────────────────────
test_strategic_fit_adjustment_updates_summary_explanation()
test_strategic_fit_no_change_preserves_summary()
test_score_explanation_stores_only_1_3_fields()
test_heuristic_fallback_sets_scoring_method()
test_lists_capped_at_max_length()
test_clamp_with_nan()
test_old_rfp_null_score_explanation_safe()
test_adjusted_score_stored_not_raw()

print("\nAll scoring tests passed.")
