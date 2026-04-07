"""
Unit tests for services/scoring.py

LLM calls are mocked — no Anthropic API key required.
Tests cover:
  - _heuristic_score: structure, keyword matching
  - score_bid: BID decision, NO BID decision, heuristic fallback, string input
  - Result schema validation
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services.scoring import _heuristic_score, score_bid

# ── Helpers ────────────────────────────────────────────────────────────────

_INDUSTRY_CTX = {
    "vendor_type": "IT vendor",
    "relevant_domains": ["software", "cloud", "infrastructure"],
}


def _fake_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _score_payload(**overrides) -> str:
    base = {
        "relevance_score": 80,
        "budget_fit": 75,
        "requirements_match": 85,
        "completeness": 70,
        "reasoning": "Strong match with vendor capabilities.",
    }
    base.update(overrides)
    return json.dumps(base)


# ── _heuristic_score ───────────────────────────────────────────────────────

def test_heuristic_score_returns_all_required_keys():
    result = _heuristic_score("generic services project", _INDUSTRY_CTX)
    required = {"relevance_score", "budget_fit", "requirements_match",
                "completeness", "reasoning"}
    assert required.issubset(result.keys())


def test_heuristic_score_all_values_in_range():
    result = _heuristic_score("cloud services solution delivery", _INDUSTRY_CTX)
    for key in ("relevance_score", "budget_fit", "requirements_match", "completeness"):
        assert 0 <= result[key] <= 100, f"{key} out of range: {result[key]}"


def test_heuristic_score_higher_for_keyword_rich_text():
    rich = "cloud software infrastructure delivery service solution support consulting"
    sparse = "unrelated boilerplate document with no matching terms whatsoever"
    r_rich = _heuristic_score(rich, _INDUSTRY_CTX)
    r_sparse = _heuristic_score(sparse, _INDUSTRY_CTX)
    assert r_rich["relevance_score"] >= r_sparse["relevance_score"]


def test_heuristic_score_budget_fit_higher_when_budget_mentioned():
    with_budget = "The project budget is USD 200,000 for service delivery."
    no_budget = "Scope of work includes several deliverables."
    r_with = _heuristic_score(with_budget, _INDUSTRY_CTX)
    r_without = _heuristic_score(no_budget, _INDUSTRY_CTX)
    assert r_with["budget_fit"] >= r_without["budget_fit"]


def test_heuristic_score_completeness_higher_for_long_text():
    long_text = "detailed requirement " * 100   # > 1000 chars
    short_text = "brief"
    r_long = _heuristic_score(long_text, _INDUSTRY_CTX)
    r_short = _heuristic_score(short_text, _INDUSTRY_CTX)
    assert r_long["completeness"] > r_short["completeness"]


# ── score_bid ─────────────────────────────────────────────────────────────

def test_score_bid_returns_bid_when_weighted_score_above_threshold():
    # weights: relevance=0.30, budget=0.25, match=0.25, completeness=0.20
    # 80*0.30 + 75*0.25 + 85*0.25 + 70*0.20 = 24+18.75+21.25+14 = 78 → BID
    payload = _score_payload(
        relevance_score=80, budget_fit=75, requirements_match=85, completeness=70
    )
    with patch("services.scoring.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        result = score_bid({"requirements": [{"text": "Cloud migration"}]})

    assert result["decision"] == "BID"
    assert result["score"] >= 60


def test_score_bid_returns_no_bid_when_weighted_score_below_threshold():
    # 30*0.30 + 35*0.25 + 30*0.25 + 25*0.20 = 9+8.75+7.5+5 = 30.25 → NO BID
    payload = _score_payload(
        relevance_score=30, budget_fit=35, requirements_match=30, completeness=25
    )
    with patch("services.scoring.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        result = score_bid({"requirements": []})

    assert result["decision"] == "NO BID"
    assert result["score"] < 60


def test_score_bid_result_schema():
    payload = _score_payload()
    with patch("services.scoring.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        result = score_bid({"requirements": []})

    assert "score" in result
    assert "decision" in result
    assert "breakdown" in result
    assert "reasoning" in result
    assert "weights_used" in result
    assert "threshold_used" in result
    assert result["decision"] in ("BID", "NO BID")
    assert 0 <= result["score"] <= 100


def test_score_bid_falls_back_to_heuristic_when_llm_raises():
    with patch("services.scoring.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("API unavailable")

        result = score_bid("Cloud services RFP with budget and experience requirements")

    # Heuristic fallback must still return a valid result
    assert "score" in result
    assert result["decision"] in ("BID", "NO BID")
    assert 0 <= result["score"] <= 100


def test_score_bid_accepts_string_input():
    payload = _score_payload()
    with patch("services.scoring.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        # Should not raise even with a plain string
        result = score_bid("plain text RFP description")

    assert "score" in result


def test_score_bid_breakdown_matches_llm_values():
    payload = _score_payload(
        relevance_score=90, budget_fit=80, requirements_match=75, completeness=65
    )
    with patch("services.scoring.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        result = score_bid({})

    bd = result["breakdown"]
    assert bd["relevance_score"] == 90
    assert bd["budget_fit"] == 80
    assert bd["requirements_match"] == 75
    assert bd["completeness"] == 65
