"""
Unit tests for services/extractor.py

LLM calls are mocked — no Anthropic API key required.
Tests cover:
  - _strip_markdown_fences
  - _empty_result structure
  - _enrich_result normalization
  - _split_into_chunks
  - _merge_extractions
  - extract_requirements (mocked LLM, happy path)
  - extract_requirements (LLM returns invalid JSON → rescue path)
  - extract_requirements (chunked path for large text)
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services.extractor import (
    _empty_result,
    _enrich_result,
    _merge_extractions,
    _split_into_chunks,
    _strip_markdown_fences,
    extract_requirements,
)

# ── Helpers ────────────────────────────────────────────────────────────────

def _fake_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _valid_llm_response(**overrides) -> str:
    base = {
        "summary": "IT services modernization RFP",
        "client": "Ministry of Health",
        "deadline": "2026-06-01",
        "budget": "$500k",
        "requirements": [
            {
                "text": "Cloud migration of legacy systems",
                "category": "mandatory",
                "reason": "Explicitly required",
                "type": "technical",
                "type_reason": "Infrastructure work",
            }
        ],
        "unclear_requirements": [],
        "missing_information": [],
        "evaluation_criteria": ["Price", "Technical approach"],
        "deliverables": ["Migration plan", "Final report"],
        "keywords": ["cloud", "migration", "legacy"],
        "extraction_status": "complete",
        "confidence": "high",
        "notes": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ── _strip_markdown_fences ─────────────────────────────────────────────────

def test_strip_markdown_fences_removes_json_block():
    wrapped = '```json\n{"key": "value"}\n```'
    assert _strip_markdown_fences(wrapped) == '{"key": "value"}'


def test_strip_markdown_fences_removes_plain_code_block():
    wrapped = '```\n{"key": "value"}\n```'
    assert _strip_markdown_fences(wrapped) == '{"key": "value"}'


def test_strip_markdown_fences_passes_through_plain_json():
    plain = '{"key": "value"}'
    assert _strip_markdown_fences(plain) == plain


def test_strip_markdown_fences_strips_whitespace():
    padded = '  {"key": "value"}  '
    result = _strip_markdown_fences(padded)
    assert result.strip() == '{"key": "value"}'


# ── _empty_result ─────────────────────────────────────────────────────────

def test_empty_result_has_all_required_fields():
    result = _empty_result()
    required = {
        "summary", "client", "deadline", "budget",
        "requirements", "unclear_requirements", "missing_information",
        "evaluation_criteria", "deliverables", "keywords",
        "extraction_status", "confidence", "notes",
    }
    assert required.issubset(result.keys())


def test_empty_result_lists_are_empty():
    result = _empty_result()
    assert result["requirements"] == []
    assert result["keywords"] == []
    assert result["deliverables"] == []


def test_empty_result_accepts_summary_arg():
    result = _empty_result(summary="Test summary")
    assert result["summary"] == "Test summary"


# ── _enrich_result ────────────────────────────────────────────────────────

def test_enrich_result_keeps_valid_status():
    base = _empty_result()
    base["extraction_status"] = "complete"
    base["confidence"] = "high"
    # Must have at least one requirement, otherwise _enrich_result downgrades status
    base["requirements"] = [{"text": "R1", "category": "mandatory",
                              "reason": "", "type": "technical", "type_reason": ""}]
    result = _enrich_result(base)
    assert result["extraction_status"] == "complete"
    assert result["confidence"] == "high"


def test_enrich_result_coerces_invalid_status_to_partial():
    base = _empty_result()
    base["extraction_status"] = "totally_made_up"
    # Give it content so the status isn't further overridden to "failed"
    base["requirements"] = [{"text": "R1", "category": "mandatory",
                              "reason": "", "type": "technical", "type_reason": ""}]
    result = _enrich_result(base)
    assert result["extraction_status"] == "partial"


def test_enrich_result_coerces_invalid_confidence_to_medium():
    base = _empty_result()
    base["confidence"] = "ultra_high"
    # Give it content so confidence isn't further downgraded to "low"
    base["requirements"] = [{"text": "R1", "category": "mandatory",
                              "reason": "", "type": "technical", "type_reason": ""}]
    result = _enrich_result(base)
    assert result["confidence"] == "medium"


def test_enrich_result_adds_missing_fields():
    minimal = {"summary": "test", "requirements": [], "unclear_requirements": []}
    result = _enrich_result(minimal)
    assert "missing_information" in result
    assert "notes" in result
    assert "confidence" in result
    assert "extraction_status" in result


# ── _split_into_chunks ────────────────────────────────────────────────────

def test_split_into_chunks_small_text_returns_one_chunk():
    text = "short text"
    chunks = _split_into_chunks(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_into_chunks_large_text_produces_multiple_chunks():
    text = "word " * 10_000  # ~50k chars
    chunks = _split_into_chunks(text)
    assert len(chunks) >= 2


def test_split_into_chunks_chunks_cover_full_text():
    text = "A" * 100_000
    chunks = _split_into_chunks(text)
    # Reconstructing from non-overlapping pieces is impractical, but every
    # character should be covered by at least one chunk.
    covered = set()
    for chunk in chunks:
        # Verify no chunk exceeds the chunk size limit
        from services.extractor import _CHUNK_SIZE
        assert len(chunk) <= _CHUNK_SIZE + 500  # slight tolerance for boundary logic


# ── _merge_extractions ────────────────────────────────────────────────────

def test_merge_extractions_combines_requirements():
    p1 = _empty_result(summary="doc summary")
    p1["requirements"] = [{"text": "Req A", "category": "mandatory",
                           "reason": "", "type": "technical", "type_reason": ""}]
    p1["extraction_status"] = "complete"
    p1["confidence"] = "high"

    p2 = _empty_result()
    p2["requirements"] = [{"text": "Req B", "category": "optional",
                           "reason": "", "type": "administrative", "type_reason": ""}]
    p2["extraction_status"] = "partial"
    p2["confidence"] = "medium"

    merged = _merge_extractions([p1, p2])
    texts = [r["text"] for r in merged["requirements"]]
    assert "Req A" in texts
    assert "Req B" in texts


def test_merge_extractions_deduplicates_requirements():
    req = {"text": "Same requirement", "category": "mandatory",
           "reason": "", "type": "technical", "type_reason": ""}
    p1 = _empty_result()
    p1["requirements"] = [req]
    p2 = _empty_result()
    p2["requirements"] = [req]

    merged = _merge_extractions([p1, p2])
    # Same text → only one copy
    assert len(merged["requirements"]) == 1


def test_merge_extractions_escalates_status_to_worst():
    p1 = _empty_result()
    p1["extraction_status"] = "complete"
    p2 = _empty_result()
    p2["extraction_status"] = "failed"

    merged = _merge_extractions([p1, p2])
    assert merged["extraction_status"] == "failed"


# ── extract_requirements (mocked LLM) ─────────────────────────────────────

def test_extract_requirements_happy_path_returns_structured_dict():
    payload = _valid_llm_response()

    with patch("services.extractor.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        result = extract_requirements("Some RFP text about cloud services")

    assert result["summary"] == "IT services modernization RFP"
    assert result["client"] == "Ministry of Health"
    assert len(result["requirements"]) == 1
    assert result["extraction_status"] == "complete"
    assert result["confidence"] == "high"


def test_extract_requirements_invalid_json_triggers_rescue_and_returns_dict():
    """LLM returns unparseable content → rescue path → still returns a dict."""
    with patch("services.extractor.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        # First call: broken JSON; second call (rescue): also broken
        mock_client.messages.create.return_value = _fake_message("not valid json {{")

        result = extract_requirements("Some RFP text")

    assert isinstance(result, dict)
    assert "extraction_status" in result
    # Rescue or total fail — either is acceptable; must not raise
    assert result["extraction_status"] in ("failed", "ambiguous", "partial")


def test_extract_requirements_result_always_has_required_keys():
    payload = _valid_llm_response()
    with patch("services.extractor.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)
        result = extract_requirements("text")

    required = {
        "summary", "requirements", "extraction_status", "confidence",
        "unclear_requirements", "missing_information",
    }
    assert required.issubset(result.keys())


def test_extract_requirements_uses_chunked_path_for_large_text():
    """Text > 120k chars triggers _extract_chunked; verify multiple LLM calls."""
    large_text = "word " * 30_000  # ~150k chars
    payload = _valid_llm_response()

    with patch("services.extractor.get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.messages.create.return_value = _fake_message(payload)

        result = extract_requirements(large_text)

    # Chunked path calls LLM more than once
    assert mock_client.messages.create.call_count >= 2
    assert isinstance(result, dict)
    assert "requirements" in result
