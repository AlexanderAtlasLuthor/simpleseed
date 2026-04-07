"""
Integration tests for the FastAPI endpoints.

Uses an in-memory SQLite DB (via http_client fixture in conftest.py).
LLM / pipeline service calls are mocked where needed so no real API
calls are made.
"""
import io
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


# ── /api/health ────────────────────────────────────────────────────────────

async def test_health_returns_ok(http_client: AsyncClient):
    resp = await http_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── /api/industries ────────────────────────────────────────────────────────

async def test_industries_returns_list(http_client: AsyncClient):
    resp = await http_client.get("/api/industries")
    assert resp.status_code == 200
    data = resp.json()
    assert "industries" in data
    assert isinstance(data["industries"], list)
    assert len(data["industries"]) > 0
    # Each entry must have id and label
    for item in data["industries"]:
        assert "id" in item
        assert "label" in item


# ── /api/rfps ─────────────────────────────────────────────────────────────

async def test_list_rfps_returns_empty_list_on_fresh_db(http_client: AsyncClient):
    resp = await http_client.get("/api/rfps")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_rfp_not_found_returns_404(http_client: AsyncClient):
    resp = await http_client.get("/api/rfps/nonexistent-id-12345")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_delete_nonexistent_rfp_returns_404(http_client: AsyncClient):
    resp = await http_client.delete("/api/rfps/does-not-exist")
    assert resp.status_code == 404


# ── /api/rfps/{rfp_id}/feedback ────────────────────────────────────────────

async def test_add_feedback_invalid_outcome_returns_422(http_client: AsyncClient):
    resp = await http_client.post(
        "/api/rfps/some-rfp/feedback",
        json={"outcome": "invalid_outcome"},
    )
    assert resp.status_code == 422


async def test_add_feedback_valid_outcome_creates_record(http_client: AsyncClient):
    """Feedback can be recorded even for non-existent RFPs (rfp_id is nullable FK)."""
    resp = await http_client.post(
        "/api/rfps/any-rfp-id/feedback",
        json={"outcome": "won", "notes": "Great result"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "won"
    assert "id" in data


async def test_list_feedback_for_rfp_returns_list(http_client: AsyncClient):
    rfp_id = "test-rfp-feedback"
    # Create one feedback entry
    await http_client.post(
        f"/api/rfps/{rfp_id}/feedback",
        json={"outcome": "lost"},
    )
    resp = await http_client.get(f"/api/rfps/{rfp_id}/feedback")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert items[0]["outcome"] == "lost"


# ── /api/feedback ─────────────────────────────────────────────────────────

async def test_list_feedback_returns_empty_list_on_fresh_db(http_client: AsyncClient):
    resp = await http_client.get("/api/feedback")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_feedback_summary_returns_expected_keys(http_client: AsyncClient):
    resp = await http_client.get("/api/feedback/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_feedback_records" in data


async def test_list_feedback_limit_query_param(http_client: AsyncClient):
    resp = await http_client.get("/api/feedback?limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_feedback_invalid_limit_returns_422(http_client: AsyncClient):
    resp = await http_client.get("/api/feedback?limit=0")
    assert resp.status_code == 422


# ── /api/knowledge ────────────────────────────────────────────────────────

async def test_list_knowledge_returns_empty_list_on_fresh_db(http_client: AsyncClient):
    resp = await http_client.get("/api/knowledge")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_unknown_knowledge_doc_returns_404(http_client: AsyncClient):
    resp = await http_client.get("/api/knowledge/no-such-doc")
    assert resp.status_code == 404


async def test_upload_knowledge_txt_document(http_client: AsyncClient):
    content = b"This is a plain-text knowledge document about cloud services."
    files = {"file": ("kb_doc.txt", io.BytesIO(content), "text/plain")}
    resp = await http_client.post("/api/knowledge", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "document_id" in data


# ── /api/analyze ─────────────────────────────────────────────────────────

async def test_analyze_rejects_non_pdf_file(http_client: AsyncClient):
    content = b"This is a text file"
    files = {"file": ("doc.txt", io.BytesIO(content), "text/plain")}
    resp = await http_client.post("/api/analyze", files=files)
    assert resp.status_code == 400
    assert "pdf" in resp.json()["detail"].lower()


async def test_analyze_pdf_runs_full_pipeline_with_mocked_services(http_client: AsyncClient):
    """
    End-to-end test for POST /api/analyze.
    All LLM and parsing calls are mocked; the DB write is real (in-memory SQLite).
    """
    fake_requirements = {
        "summary": "IT modernisation project",
        "client": "Test Agency",
        "deadline": "2026-12-01",
        "budget": "$1M",
        "requirements": [{"text": "Cloud hosting", "category": "mandatory",
                          "reason": "", "type": "technical", "type_reason": ""}],
        "unclear_requirements": [],
        "missing_information": [],
        "evaluation_criteria": ["Price", "Experience"],
        "deliverables": ["Final system"],
        "keywords": ["cloud"],
        "extraction_status": "complete",
        "confidence": "high",
        "notes": None,
    }
    fake_proposal = {
        "proposal": "We propose a comprehensive cloud migration solution...",
        "information_gaps": [],
        "unsupported_claims_avoided": [],
        "evidence_used": [],
    }
    fake_score = {
        "score": 75,
        "decision": "BID",
        "breakdown": {"relevance_score": 80, "budget_fit": 70,
                      "requirements_match": 80, "completeness": 65},
        "reasoning": "Strong fit.",
        "weights_used": {},
        "threshold_used": 60,
    }
    fake_strategic_fit = {"status": "unknown"}

    # Minimal fake PDF bytes (just needs to pass the size check)
    fake_pdf_bytes = b"%PDF-1.4 fake content"

    with patch("main.parse_pdf", return_value="Cloud IT services RFP with lots of content"), \
         patch("main.extract_requirements", return_value=fake_requirements), \
         patch("main.identify_risks", return_value=[]), \
         patch("main.search_knowledge", return_value=[]), \
         patch("main.generate_proposal", return_value=fake_proposal), \
         patch("main.score_bid", return_value=fake_score), \
         patch("main.evaluate_strategic_fit", return_value=fake_strategic_fit):

        files = {"file": ("rfp.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")}
        resp = await http_client.post("/api/analyze", files=files)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "id" in data
    assert data["score"]["decision"] == "BID"
    assert data["score"]["score"] == 75

    # Verify the record was persisted in the test DB
    rfp_id = data["id"]
    get_resp = await http_client.get(f"/api/rfps/{rfp_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rfp_id


async def test_analyze_pdf_appears_in_rfp_list_after_creation(http_client: AsyncClient):
    """After a successful analysis, GET /api/rfps must include the new record."""
    fake_requirements = {
        "summary": "Summary", "client": None, "deadline": None, "budget": None,
        "requirements": [], "unclear_requirements": [], "missing_information": [],
        "evaluation_criteria": [], "deliverables": [], "keywords": [],
        "extraction_status": "complete", "confidence": "medium", "notes": None,
    }
    fake_proposal = {"proposal": "Proposal text", "information_gaps": [],
                     "unsupported_claims_avoided": [], "evidence_used": []}
    fake_score = {"score": 55, "decision": "NO BID", "breakdown": {},
                  "reasoning": "", "weights_used": {}, "threshold_used": 60}

    with patch("main.parse_pdf", return_value="Short RFP text for services"), \
         patch("main.extract_requirements", return_value=fake_requirements), \
         patch("main.identify_risks", return_value=[]), \
         patch("main.search_knowledge", return_value=[]), \
         patch("main.generate_proposal", return_value=fake_proposal), \
         patch("main.score_bid", return_value=fake_score), \
         patch("main.evaluate_strategic_fit", return_value={"status": "unknown"}):

        files = {"file": ("rfp2.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
        resp = await http_client.post("/api/analyze", files=files)

    assert resp.status_code == 200
    rfp_id = resp.json()["id"]

    list_resp = await http_client.get("/api/rfps")
    ids = [r["id"] for r in list_resp.json()]
    assert rfp_id in ids


# ── /api/scoring-config ────────────────────────────────────────────────────

async def test_get_scoring_config_returns_expected_keys(http_client: AsyncClient):
    resp = await http_client.get("/api/scoring-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "weights" in data
    assert "bid_threshold" in data
    assert "strategic_fit_weight" in data


async def test_update_scoring_config_invalid_weights_returns_422(http_client: AsyncClient):
    bad_config = {
        "weights": {
            "relevance_score": 0.50,
            "budget_fit": 0.50,
            "requirements_match": 0.50,  # sum > 1.0
            "completeness": 0.50,
        },
        "bid_threshold": 60.0,
        "strategic_fit_weight": 0.20,
    }
    resp = await http_client.put("/api/scoring-config", json=bad_config)
    assert resp.status_code == 422
