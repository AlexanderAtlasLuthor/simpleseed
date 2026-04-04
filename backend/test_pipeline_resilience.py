"""
Verify that _run_analysis() is resilient to per-step LLM failures.

Strategy:
- Use an in-memory SQLite DB (same pattern as other test files)
- Mock individual service functions to raise on demand
- Confirm that already-committed step results survive when a later step fails

No real LLM calls.  All three steps are mocked.
"""
import sys, json, asyncio
from unittest.mock import patch, MagicMock

# Stub modules that require native deps not available in the test environment.
# Must happen before `import main`.
for _mod in ["pdfplumber", "services.parser", "services.fetcher", "services.sam_gov"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, ".")

# ── Minimal in-memory DB ─────────────────────────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models.rfp import RFP            # noqa: F401
from models.feedback import Feedback  # noqa: F401
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
    "requirements": [{"text": "HIPAA-compliant pipelines", "category": "mandatory"}],
    "deliverables": ["Cloud platform"],
    "evaluation_criteria": ["Technical approach"],
    "keywords": ["healthcare", "cloud", "HIPAA"],
    "extraction_status": "complete",
    "confidence": "high",
    "unclear_requirements": [],
    "missing_information": [],
    "notes": None,
}

MOCK_PROPOSAL_RESULT = {
    "proposal": "MOCK PROPOSAL TEXT",
    "information_gaps": ["No past performance in KB"],
    "unsupported_claims_avoided": ["Did not claim certification"],
    "evidence_used": [{"source": "rfp", "snippet": "HIPAA-compliant pipelines"}],
}

MOCK_SCORE = {
    "score": 72,
    "decision": "BID",
    "breakdown": {
        "relevance_score": 80, "budget_fit": 70,
        "requirements_match": 70, "completeness": 65,
    },
    "reasoning": "Good fit.",
    "weights_used": {},
    "threshold_used": 60,
}

MOCK_RISKS = [
    {"title": "Tight deadline", "severity": "medium", "category": "deadline",
     "description": "30-day window.", "evidence": "deadline stated"},
]


# ── Generic run helper ────────────────────────────────────────────────────────

async def _run_analysis(
    extract_effect=None,
    proposal_effect=None,
    score_effect=None,
    extract_return=None,
    proposal_return=None,
    score_return=None,
):
    """Run _run_analysis with all service calls mocked, zero retry delay."""
    import main as main_mod

    # Patch _llm_with_retry to use zero delay so tests don't sleep
    original_retry = main_mod._llm_with_retry
    async def fast_retry(fn, *args, max_retries=1, retry_delay=0.0, **kwargs):
        return await original_retry(fn, *args, max_retries=max_retries, retry_delay=0.0, **kwargs)

    db = _new_db()
    try:
        with patch.object(main_mod, "extract_requirements",
                          side_effect=extract_effect,
                          return_value=extract_return or MOCK_REQUIREMENTS), \
             patch.object(main_mod, "generate_proposal",
                          side_effect=proposal_effect,
                          return_value=proposal_return or MOCK_PROPOSAL_RESULT), \
             patch.object(main_mod, "score_bid",
                          side_effect=score_effect,
                          return_value=score_return or MOCK_SCORE), \
             patch.object(main_mod, "identify_risks",   return_value=MOCK_RISKS), \
             patch.object(main_mod, "search_knowledge", return_value=[]), \
             patch.object(main_mod, "load_profile",     return_value=None), \
             patch.object(main_mod, "evaluate_strategic_fit",
                          return_value={"status": "unknown"}), \
             patch.object(main_mod, "_llm_with_retry", fast_retry):
            result = await main_mod._run_analysis(
                text="Healthcare RFP content with enough text to pass validation",
                filename="test.pdf",
                db=db,
                industry="healthcare",
            )
        return result, db
    except Exception:
        db.close()
        raise


# ═══════════════════════════════════════════════════════════════════════════
# Case 1: All steps succeed → status="completed", all fields populated
# ═══════════════════════════════════════════════════════════════════════════
async def case1():
    result, db = await _run_analysis()
    try:
        assert result["status"] == "completed", f"Expected completed, got {result['status']}"
        assert result["failed_step"] is None
        assert set(result["completed_steps"]) == {
            "requirement_extraction", "proposal_generation", "bid_scoring"
        }
        assert result["requirements"] is not None
        assert result["proposal"] == "MOCK PROPOSAL TEXT"
        assert result["score"]["score"] == 72
        assert result["error"] is None

        rfp = db.query(RFP).filter(RFP.id == result["id"]).first()
        assert rfp.pipeline_status == "completed"
        assert rfp.failed_step is None
        assert rfp.proposal == "MOCK PROPOSAL TEXT"
        assert rfp.score == 72
    finally:
        db.close()
    print("Case 1 PASS: all steps succeed → completed, all fields in DB")


# ═══════════════════════════════════════════════════════════════════════════
# Case 2: Step 2 (proposal_generation) fails → step 1 results preserved
# ═══════════════════════════════════════════════════════════════════════════
async def case2():
    result, db = await _run_analysis(proposal_effect=RuntimeError("Anthropic API timeout"))
    try:
        assert result["status"] == "partial_failure"
        assert result["failed_step"] == "proposal_generation"
        assert result["completed_steps"] == ["requirement_extraction"]

        # Step 1 results must be present
        assert result["requirements"] is not None
        assert result["requirements"]["summary"] == MOCK_REQUIREMENTS["summary"]
        assert result["risks"] is not None

        # Steps 2 and 3 must be null/empty
        assert result["proposal"] is None or result["proposal"] == ""
        assert result["score"] is None

        # Error is structured
        assert result["error"]["type"] == "RuntimeError"
        assert "timeout" in result["error"]["message"].lower()

        # DB: step 1 committed, step 2 never committed
        rfp = db.query(RFP).filter(RFP.id == result["id"]).first()
        assert rfp.pipeline_status == "partial_failure"
        assert rfp.failed_step == "proposal_generation"
        reqs = json.loads(rfp.requirements)
        assert reqs.get("summary") == MOCK_REQUIREMENTS["summary"]
        assert rfp.proposal is None
    finally:
        db.close()
    print("Case 2 PASS: proposal_generation failure → step 1 preserved in DB and response")


# ═══════════════════════════════════════════════════════════════════════════
# Case 3: Step 3 (bid_scoring) fails → steps 1 and 2 preserved
# ═══════════════════════════════════════════════════════════════════════════
async def case3():
    result, db = await _run_analysis(score_effect=ConnectionError("LLM service unavailable"))
    try:
        assert result["status"] == "partial_failure"
        assert result["failed_step"] == "bid_scoring"
        assert set(result["completed_steps"]) == {"requirement_extraction", "proposal_generation"}

        assert result["requirements"] is not None
        assert result["proposal"] == "MOCK PROPOSAL TEXT"
        assert result["score"] is None

        assert result["error"]["type"] == "ConnectionError"

        rfp = db.query(RFP).filter(RFP.id == result["id"]).first()
        assert rfp.pipeline_status == "partial_failure"
        assert rfp.failed_step == "bid_scoring"
        assert rfp.proposal == "MOCK PROPOSAL TEXT"
        assert rfp.score == 0   # default — step 3 never ran
    finally:
        db.close()
    print("Case 3 PASS: bid_scoring failure → steps 1+2 preserved in DB and response")


# ═══════════════════════════════════════════════════════════════════════════
# Case 4: Step 1 (requirement_extraction) fails → record still created
# ═══════════════════════════════════════════════════════════════════════════
async def case4():
    result, db = await _run_analysis(extract_effect=ValueError("LLM returned invalid JSON"))
    try:
        assert result["status"] == "partial_failure"
        assert result["failed_step"] == "requirement_extraction"
        assert result["completed_steps"] == []
        assert result["score"] is None
        assert result["error"]["type"] == "ValueError"

        rfp = db.query(RFP).filter(RFP.id == result["id"]).first()
        assert rfp is not None, "Record must exist even when step 1 fails"
        assert rfp.pipeline_status == "partial_failure"
        assert rfp.failed_step == "requirement_extraction"
    finally:
        db.close()
    print("Case 4 PASS: step 1 failure → record persisted with failure state")


# ═══════════════════════════════════════════════════════════════════════════
# Case 5: error object has correct shape in all three failure cases
# ═══════════════════════════════════════════════════════════════════════════
async def case5():
    cases = [
        ("requirement_extraction", {"extract_effect":  OSError("disk full")}),
        ("proposal_generation",    {"proposal_effect": TimeoutError("LLM timeout")}),
        ("bid_scoring",            {"score_effect":    MemoryError("OOM")}),
    ]
    for step, kwargs in cases:
        result, db = await _run_analysis(**kwargs)
        db.close()
        assert result["failed_step"] == step
        err = result["error"]
        assert isinstance(err, dict)
        assert "type" in err and "message" in err
        assert isinstance(err["type"], str)
        assert isinstance(err["message"], str)
        assert len(err["message"]) <= 500
    print("Case 5 PASS: error object shape is correct in all 3 failure scenarios")


# ═══════════════════════════════════════════════════════════════════════════
# Case 6: retry — step succeeds on 2nd attempt, status = "completed"
# ═══════════════════════════════════════════════════════════════════════════
async def case6():
    import main as main_mod

    call_count = {"n": 0}
    def flaky_extract(text):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient LLM failure")
        return MOCK_REQUIREMENTS

    original_retry = main_mod._llm_with_retry
    async def fast_retry(fn, *args, max_retries=1, retry_delay=0.0, **kwargs):
        return await original_retry(fn, *args, max_retries=max_retries, retry_delay=0.0, **kwargs)

    db = _new_db()
    try:
        with patch.object(main_mod, "extract_requirements", side_effect=flaky_extract), \
             patch.object(main_mod, "generate_proposal",    return_value=MOCK_PROPOSAL_RESULT), \
             patch.object(main_mod, "score_bid",            return_value=MOCK_SCORE), \
             patch.object(main_mod, "identify_risks",       return_value=MOCK_RISKS), \
             patch.object(main_mod, "search_knowledge",     return_value=[]), \
             patch.object(main_mod, "load_profile",         return_value=None), \
             patch.object(main_mod, "evaluate_strategic_fit", return_value={"status": "unknown"}), \
             patch.object(main_mod, "_llm_with_retry", fast_retry):
            result = await main_mod._run_analysis(
                text="Healthcare RFP content enough text",
                filename="test.pdf", db=db, industry="healthcare",
            )
        assert result["status"] == "completed", \
            f"Should complete after retry, got: {result['status']}"
        assert call_count["n"] == 2, \
            f"Should have been called twice (fail + retry), got {call_count['n']}"
    finally:
        db.close()
    print(f"Case 6 PASS: transient failure retried once → final status=completed")


# ═══════════════════════════════════════════════════════════════════════════
# Case 7: partial response has all required keys in every failure case
# ═══════════════════════════════════════════════════════════════════════════
async def case7():
    required_keys = {
        "id", "filename", "status", "failed_step", "completed_steps",
        "industry", "requirements", "risks", "strategic_fit", "proposal",
        "score", "knowledge_results", "knowledge_used", "knowledge_status",
        "evidence_used", "information_gaps", "unsupported_claims_avoided",
        "grounding_status", "error", "created_at",
    }
    for step, kwargs in [
        ("requirement_extraction", {"extract_effect":  RuntimeError("fail")}),
        ("proposal_generation",    {"proposal_effect": RuntimeError("fail")}),
        ("bid_scoring",            {"score_effect":    RuntimeError("fail")}),
    ]:
        result, db = await _run_analysis(**kwargs)
        db.close()
        missing = required_keys - result.keys()
        assert not missing, f"Step '{step}' failure response missing keys: {missing}"
    print(f"Case 7 PASS: partial response has all {len(required_keys)} required keys in all 3 cases")


# ── Run all ──────────────────────────────────────────────────────────────────
asyncio.run(case1())
asyncio.run(case2())
asyncio.run(case3())
asyncio.run(case4())
asyncio.run(case5())
asyncio.run(case6())
asyncio.run(case7())

print("\nAll cases passed.")
