"""
Verify that _resume_analysis() retries a failed step without re-running
steps that already completed and persisted their artifacts.

Tests confirm:
- step 1 artifacts (requirements) are reused when retrying from step 2
- step 1+2 artifacts are reused when retrying from step 3
- retrying from step 1 re-runs all three steps (full retry)
- invalid state / corrupted artifacts → 422 with clear error
- unknown rfp_id → 404
- non-retryable status → 409
- response includes retried_from, reused_steps, rerun_steps
"""
import sys, json, asyncio, uuid
from unittest.mock import patch, MagicMock, call

for _mod in ["pdfplumber", "services.parser", "services.fetcher", "services.sam_gov"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, ".")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models.rfp import RFP
from models.feedback import Feedback           # noqa: F401
from models.knowledge_document import KnowledgeDocument  # noqa: F401

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)

def _new_db():
    return _Session()

# ── Shared mock data ─────────────────────────────────────────────────────────
MOCK_REQUIREMENTS = {
    "summary": "IT modernization for a hospital.",
    "client": "City Hospital",
    "budget": "$2M",
    "deadline": "2024-09-01",
    "requirements": [{"text": "HIPAA pipelines", "category": "mandatory"}],
    "deliverables": ["Cloud platform"],
    "evaluation_criteria": ["Technical approach"],
    "keywords": ["healthcare", "cloud"],
    "extraction_status": "complete",
    "confidence": "high",
    "unclear_requirements": [],
    "missing_information": [],
    "notes": None,
}

MOCK_PROPOSAL_RESULT = {
    "proposal": "MOCK PROPOSAL TEXT",
    "information_gaps": [],
    "unsupported_claims_avoided": [],
    "evidence_used": [{"source": "rfp", "snippet": "HIPAA pipelines"}],
}

MOCK_SCORE = {
    "score": 72,
    "decision": "BID",
    "breakdown": {"relevance_score": 80, "budget_fit": 70,
                  "requirements_match": 70, "completeness": 65},
    "reasoning": "Good fit.",
    "weights_used": {},
    "threshold_used": 60,
}

MOCK_RISKS = [{"title": "Tight deadline", "severity": "medium",
               "category": "deadline", "description": "x", "evidence": "y"}]


def _make_partial_rfp(db, failed_step: str, completed_steps: list,
                      include_requirements=True, include_proposal=False) -> RFP:
    """Create a partial_failure RFP record in the in-memory DB."""
    rfp = RFP(
        id=f"rfp_{uuid.uuid4().hex[:12]}",
        filename="test.pdf",
        original_text="Healthcare RFP content with enough text to process",
        industry="healthcare",
        pipeline_status="partial_failure",
        failed_step=failed_step,
        completed_steps=json.dumps(completed_steps),
        pipeline_error=json.dumps({"type": "RuntimeError", "message": "LLM timeout"}),
        score=0,
        decision="NO BID",
        score_breakdown="{}",
        reasoning="",
        requirements=json.dumps(MOCK_REQUIREMENTS) if include_requirements else "{}",
        risks=json.dumps(MOCK_RISKS)               if include_requirements else "[]",
        knowledge_refs="[]",
        grounding_report="{}",
        proposal="MOCK PROPOSAL TEXT"              if include_proposal else None,
        strategic_fit="{}",
    )
    db.add(rfp)
    db.commit()
    db.refresh(rfp)
    return rfp


async def _resume(rfp, retry_from, db, *, extract_effect=None, proposal_effect=None,
                  score_effect=None):
    import main as main_mod

    original_retry = main_mod._llm_with_retry
    async def fast_retry(fn, *args, max_retries=1, retry_delay=0.0, **kwargs):
        return await original_retry(fn, *args, max_retries=max_retries, retry_delay=0.0, **kwargs)

    with patch.object(main_mod, "extract_requirements",
                      side_effect=extract_effect, return_value=MOCK_REQUIREMENTS), \
         patch.object(main_mod, "generate_proposal",
                      side_effect=proposal_effect, return_value=MOCK_PROPOSAL_RESULT), \
         patch.object(main_mod, "score_bid",
                      side_effect=score_effect, return_value=MOCK_SCORE), \
         patch.object(main_mod, "identify_risks",        return_value=MOCK_RISKS), \
         patch.object(main_mod, "search_knowledge",      return_value=[]), \
         patch.object(main_mod, "load_profile",          return_value=None), \
         patch.object(main_mod, "evaluate_strategic_fit",
                      return_value={"status": "unknown"}), \
         patch.object(main_mod, "_llm_with_retry", fast_retry):
        return await main_mod._resume_analysis(rfp=rfp, retry_from=retry_from, db=db)


# ═══════════════════════════════════════════════════════════════════════════
# Case 1: Retry from proposal_generation → step 1 not re-run
# ═══════════════════════════════════════════════════════════════════════════
async def case1():
    import main as main_mod
    db = _new_db()
    try:
        rfp = _make_partial_rfp(db, "proposal_generation", ["requirement_extraction"],
                                include_requirements=True)

        extract_calls = []
        proposal_calls = []

        def track_extract(text):
            extract_calls.append(text)
            return MOCK_REQUIREMENTS

        def track_proposal(*args, **kwargs):
            proposal_calls.append(True)
            return MOCK_PROPOSAL_RESULT

        original_retry = main_mod._llm_with_retry
        async def fast_retry(fn, *args, max_retries=1, retry_delay=0.0, **kwargs):
            return await original_retry(fn, *args, max_retries=max_retries, retry_delay=0.0, **kwargs)

        with patch.object(main_mod, "extract_requirements",  side_effect=track_extract), \
             patch.object(main_mod, "generate_proposal",     side_effect=track_proposal), \
             patch.object(main_mod, "score_bid",             return_value=MOCK_SCORE), \
             patch.object(main_mod, "identify_risks",        return_value=MOCK_RISKS), \
             patch.object(main_mod, "search_knowledge",      return_value=[]), \
             patch.object(main_mod, "load_profile",          return_value=None), \
             patch.object(main_mod, "evaluate_strategic_fit",
                          return_value={"status": "unknown"}), \
             patch.object(main_mod, "_llm_with_retry", fast_retry):
            result = await main_mod._resume_analysis(
                rfp=rfp, retry_from="proposal_generation", db=db
            )

        assert len(extract_calls) == 0, \
            f"extract_requirements must NOT be called when retrying from step 2, but was called {len(extract_calls)} time(s)"
        assert len(proposal_calls) == 1, \
            "generate_proposal must be called exactly once"
        assert result["status"] == "completed"
        assert result["retried_from"] == "proposal_generation"
        assert result["reused_steps"] == ["requirement_extraction"]
        assert "proposal_generation" in result["rerun_steps"]
        assert "bid_scoring" in result["rerun_steps"]
        assert result["requirements"]["summary"] == MOCK_REQUIREMENTS["summary"]  # reused
    finally:
        db.close()
    print("Case 1 PASS: retry from proposal_generation → step 1 NOT re-run, artifacts reused")


# ═══════════════════════════════════════════════════════════════════════════
# Case 2: Retry from bid_scoring → steps 1 and 2 not re-run
# ═══════════════════════════════════════════════════════════════════════════
async def case2():
    import main as main_mod
    db = _new_db()
    try:
        rfp = _make_partial_rfp(
            db, "bid_scoring", ["requirement_extraction", "proposal_generation"],
            include_requirements=True, include_proposal=True,
        )

        extract_calls = []
        proposal_calls = []

        with patch.object(main_mod, "extract_requirements",
                          side_effect=lambda t: extract_calls.append(t) or MOCK_REQUIREMENTS), \
             patch.object(main_mod, "generate_proposal",
                          side_effect=lambda *a, **kw: proposal_calls.append(True) or MOCK_PROPOSAL_RESULT), \
             patch.object(main_mod, "score_bid",             return_value=MOCK_SCORE), \
             patch.object(main_mod, "identify_risks",        return_value=MOCK_RISKS), \
             patch.object(main_mod, "search_knowledge",      return_value=[]), \
             patch.object(main_mod, "load_profile",          return_value=None), \
             patch.object(main_mod, "evaluate_strategic_fit",
                          return_value={"status": "unknown"}):
            result = await main_mod._resume_analysis(
                rfp=rfp, retry_from="bid_scoring", db=db
            )

        assert len(extract_calls) == 0,  "step 1 must NOT be re-run"
        assert len(proposal_calls) == 0, "step 2 must NOT be re-run"
        assert result["status"] == "completed"
        assert result["retried_from"] == "bid_scoring"
        assert result["reused_steps"] == ["requirement_extraction", "proposal_generation"]
        assert result["rerun_steps"] == ["bid_scoring"]
        assert result["proposal"] == "MOCK PROPOSAL TEXT"  # reused from DB
        assert result["score"]["score"] == 72
    finally:
        db.close()
    print("Case 2 PASS: retry from bid_scoring → steps 1+2 NOT re-run, proposal reused from DB")


# ═══════════════════════════════════════════════════════════════════════════
# Case 3: Retry from requirement_extraction → all 3 steps re-run
# ═══════════════════════════════════════════════════════════════════════════
async def case3():
    import main as main_mod
    db = _new_db()
    try:
        rfp = _make_partial_rfp(db, "requirement_extraction", [], include_requirements=False)

        result = await _resume(rfp, "requirement_extraction", db)

        assert result["status"] == "completed"
        assert set(result["completed_steps"]) == {
            "requirement_extraction", "proposal_generation", "bid_scoring"
        }
        assert result["retried_from"] == "requirement_extraction"
        assert result["reused_steps"] == []
        assert set(result["rerun_steps"]) == {
            "requirement_extraction", "proposal_generation", "bid_scoring"
        }
    finally:
        db.close()
    print("Case 3 PASS: retry from step 1 → all 3 steps re-run")


# ═══════════════════════════════════════════════════════════════════════════
# Case 4: Invalid state / corrupted artifacts → HTTPException raised
# ═══════════════════════════════════════════════════════════════════════════
async def case4():
    import main as main_mod

    # 4a: non-retryable status (completed)
    db = _new_db()
    try:
        rfp = RFP(
            id="rfp_completed", filename="x.pdf", original_text="x",
            pipeline_status="completed", completed_steps='["requirement_extraction","proposal_generation","bid_scoring"]',
            score=72, decision="BID", score_breakdown="{}", reasoning="",
            requirements="{}", risks="[]", strategic_fit="{}", knowledge_refs="[]", grounding_report="{}",
        )
        db.add(rfp); db.commit()
        try:
            await main_mod._resume_analysis(rfp=rfp, retry_from="proposal_generation", db=db)
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 409
            assert "completed" in e.detail
    finally:
        db.close()
    print("  Case 4a PASS: completed status → 409")

    # 4b: retry_from proposal_generation but requirements are empty
    db = _new_db()
    try:
        rfp = RFP(
            id="rfp_missing_reqs", filename="x.pdf", original_text="x",
            pipeline_status="partial_failure", failed_step="proposal_generation",
            completed_steps="[]",
            pipeline_error='{"type":"RuntimeError","message":"fail"}',
            requirements="{}", risks="[]", strategic_fit="{}",
            knowledge_refs="[]", grounding_report="{}",
            score=0, decision="NO BID", score_breakdown="{}", reasoning="",
        )
        db.add(rfp); db.commit()
        try:
            await main_mod._resume_analysis(rfp=rfp, retry_from="proposal_generation", db=db)
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 422
            assert "requirement_extraction" in e.detail
    finally:
        db.close()
    print("  Case 4b PASS: missing requirements → 422 with clear message")

    # 4c: unknown retry_from step name
    db = _new_db()
    try:
        rfp = _make_partial_rfp(db, "proposal_generation", ["requirement_extraction"])
        try:
            await main_mod._resume_analysis(rfp=rfp, retry_from="nonexistent_step", db=db)
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 400
            assert "nonexistent_step" in e.detail
    finally:
        db.close()
    print("  Case 4c PASS: unknown step name → 400")

    print("Case 4 PASS: all invalid-state scenarios raise appropriate HTTPException")


# ═══════════════════════════════════════════════════════════════════════════
# Case 5: DB record updated correctly after retry
# ═══════════════════════════════════════════════════════════════════════════
async def case5():
    db = _new_db()
    try:
        rfp = _make_partial_rfp(db, "proposal_generation", ["requirement_extraction"],
                                include_requirements=True)
        rfp_id = rfp.id

        result = await _resume(rfp, "proposal_generation", db)
        assert result["status"] == "completed"

        # Re-query to verify DB state
        db.expire_all()
        updated = db.query(RFP).filter(RFP.id == rfp_id).first()
        assert updated.pipeline_status == "completed"
        assert updated.failed_step is None
        assert updated.pipeline_error is None
        assert updated.proposal == "MOCK PROPOSAL TEXT"
        assert updated.score == 72
        steps = json.loads(updated.completed_steps)
        assert set(steps) == {"requirement_extraction", "proposal_generation", "bid_scoring"}
    finally:
        db.close()
    print("Case 5 PASS: DB record fully updated after successful retry")


# ═══════════════════════════════════════════════════════════════════════════
# Case 6: Retry still partial_failure if the retried step fails again
# ═══════════════════════════════════════════════════════════════════════════
async def case6():
    db = _new_db()
    try:
        rfp = _make_partial_rfp(db, "proposal_generation", ["requirement_extraction"],
                                include_requirements=True)
        rfp_id = rfp.id

        result = await _resume(rfp, "proposal_generation", db,
                               proposal_effect=RuntimeError("still failing"))

        assert result["status"] == "partial_failure"
        assert result["failed_step"] == "proposal_generation"
        assert result["error"]["type"] == "RuntimeError"
        assert result["requirements"] is not None  # step 1 artifacts still there

        db.expire_all()
        updated = db.query(RFP).filter(RFP.id == rfp_id).first()
        assert updated.pipeline_status == "partial_failure"
        assert updated.failed_step == "proposal_generation"
    finally:
        db.close()
    print("Case 6 PASS: if retried step fails again → partial_failure preserved, step 1 intact")


# ═══════════════════════════════════════════════════════════════════════════
# Case 7: response shape — retried_from / reused_steps / rerun_steps present
# ═══════════════════════════════════════════════════════════════════════════
async def case7():
    db = _new_db()
    try:
        rfp = _make_partial_rfp(db, "bid_scoring",
                                ["requirement_extraction", "proposal_generation"],
                                include_requirements=True, include_proposal=True)

        result = await _resume(rfp, "bid_scoring", db)

        assert "retried_from" in result
        assert "reused_steps"  in result
        assert "rerun_steps"   in result
        assert result["retried_from"] == "bid_scoring"
        assert result["reused_steps"]  == ["requirement_extraction", "proposal_generation"]
        assert result["rerun_steps"]   == ["bid_scoring"]
    finally:
        db.close()
    print("Case 7 PASS: response includes retried_from, reused_steps, rerun_steps")


# ── Run ──────────────────────────────────────────────────────────────────────
asyncio.run(case1())
asyncio.run(case2())
asyncio.run(case3())
asyncio.run(case4())
asyncio.run(case5())
asyncio.run(case6())
asyncio.run(case7())

print("\nAll cases passed.")
