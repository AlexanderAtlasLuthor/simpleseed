"""
Unit tests for services/risks.py

LLM calls are mocked — no Anthropic API key required.
Tests cover:
  - _heuristic_risks: deadline, budget, compliance, capacity signals
  - _is_valid: valid risk, missing fields, invalid severity/category
  - _normalize: truncation, enum coercion
  - identify_risks: mocked LLM happy path, fallback on error
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services.risks import (
    VALID_CATEGORIES,
    VALID_SEVERITIES,
    _heuristic_risks,
    _is_valid,
    _normalize,
    identify_risks,
)

# ── Helpers ────────────────────────────────────────────────────────────────

def _fake_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _make_risk(**overrides) -> dict:
    base = {
        "title": "Tight submission deadline",
        "description": "Only 10 days to prepare a complete submission.",
        "severity": "high",
        "category": "deadline",
        "evidence": "Proposals due within 10 calendar days of posting.",
    }
    base.update(overrides)
    return base


# ── Constants ──────────────────────────────────────────────────────────────

def test_valid_severities_contains_expected_values():
    assert VALID_SEVERITIES == {"low", "medium", "high"}


def test_valid_categories_is_non_empty():
    assert len(VALID_CATEGORIES) >= 5


# ── _heuristic_risks ───────────────────────────────────────────────────────

def test_heuristic_risks_detects_deadline():
    risks = _heuristic_risks({"deadline": "April 15, 2026"})
    categories = [r["category"] for r in risks]
    assert "deadline" in categories


def test_heuristic_risks_detects_missing_budget():
    risks = _heuristic_risks({"budget": None, "requirements": []})
    categories = [r["category"] for r in risks]
    assert "pricing" in categories


def test_heuristic_risks_detects_compliance_keyword_hipaa():
    risks = _heuristic_risks({
        "requirements": [{"text": "Must be HIPAA compliant", "category": "mandatory"}]
    })
    categories = [r["category"] for r in risks]
    assert "compliance" in categories


def test_heuristic_risks_detects_compliance_keyword_fedramp():
    risks = _heuristic_risks({
        "requirements": [{"text": "FedRAMP authorization required", "category": "mandatory"}]
    })
    severities = {r["severity"] for r in risks if r["category"] == "compliance"}
    assert "high" in severities


def test_heuristic_risks_detects_capacity_when_many_mandatory_reqs():
    reqs = [{"text": f"Requirement {i}", "category": "mandatory"} for i in range(12)]
    risks = _heuristic_risks({"requirements": reqs})
    categories = [r["category"] for r in risks]
    assert "capacity" in categories


def test_heuristic_risks_empty_requirements_returns_at_least_pricing_risk():
    risks = _heuristic_risks({})
    # No budget present → pricing risk expected
    assert any(r["category"] == "pricing" for r in risks)


def test_heuristic_risks_all_returned_risks_are_valid():
    risks = _heuristic_risks({
        "deadline": "2026-05-01",
        "requirements": [{"text": "SOC 2 certification required", "category": "mandatory"}],
    })
    for r in risks:
        assert _is_valid(r), f"Risk failed validation: {r}"


# ── _is_valid ─────────────────────────────────────────────────────────────

def test_is_valid_accepts_correct_risk():
    assert _is_valid(_make_risk()) is True


def test_is_valid_rejects_missing_title():
    r = _make_risk()
    del r["title"]
    assert _is_valid(r) is False


def test_is_valid_rejects_empty_description():
    assert _is_valid(_make_risk(description="")) is False


def test_is_valid_rejects_invalid_severity():
    assert _is_valid(_make_risk(severity="critical")) is False


def test_is_valid_rejects_invalid_category():
    assert _is_valid(_make_risk(category="marketing")) is False


def test_is_valid_rejects_empty_evidence():
    assert _is_valid(_make_risk(evidence="")) is False


def test_is_valid_rejects_non_dict():
    assert _is_valid("not a dict") is False
    assert _is_valid(None) is False
    assert _is_valid(42) is False


# ── _normalize ────────────────────────────────────────────────────────────

def test_normalize_truncates_long_title():
    long_title = "X" * 200
    result = _normalize(_make_risk(title=long_title))
    assert len(result["title"]) <= 120


def test_normalize_truncates_long_description():
    long_desc = "Y" * 600
    result = _normalize(_make_risk(description=long_desc))
    assert len(result["description"]) <= 500


def test_normalize_truncates_long_evidence():
    long_ev = "Z" * 500
    result = _normalize(_make_risk(evidence=long_ev))
    assert len(result["evidence"]) <= 400


def test_normalize_coerces_invalid_severity_to_medium():
    result = _normalize(_make_risk(severity="extreme"))
    assert result["severity"] == "medium"


def test_normalize_coerces_invalid_category_to_scope():
    result = _normalize(_make_risk(category="unknown_cat"))
    assert result["category"] == "scope"


# ── identify_risks (mocked LLM) ────────────────────────────────────────────

def test_identify_risks_happy_path_returns_list():
    payload = json.dumps({
        "risks": [_make_risk(), _make_risk(title="Budget unclear", category="pricing",
                                           severity="medium")]
    })
    with patch("services.risks._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        risks = identify_risks({"requirements": [{"text": "HIPAA compliance"}]})

    assert isinstance(risks, list)
    assert len(risks) == 2
    assert all(_is_valid(r) for r in risks)


def test_identify_risks_filters_invalid_llm_risks():
    payload = json.dumps({
        "risks": [
            _make_risk(),                             # valid
            {"title": "", "description": "", "severity": "high",
             "category": "deadline", "evidence": ""},  # invalid (empty title/desc/evidence)
        ]
    })
    with patch("services.risks._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        risks = identify_risks({"requirements": []})

    assert len(risks) == 1  # invalid one filtered out


def test_identify_risks_falls_back_to_heuristic_when_llm_raises():
    with patch("services.risks._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("No API key")

        risks = identify_risks({"deadline": "2026-03-01", "requirements": []})

    assert isinstance(risks, list)
    # Heuristic should detect the deadline
    assert any(r["category"] == "deadline" for r in risks)


def test_identify_risks_never_raises_on_malformed_input():
    """Even with broken input, identify_risks must not propagate exceptions."""
    with patch("services.risks._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message("not json{{{")

        result = identify_risks("a plain string — not a dict")

    assert isinstance(result, list)
