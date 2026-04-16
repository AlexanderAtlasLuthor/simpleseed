import asyncio
import json
import uuid
from typing import Optional
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from config import MAX_FILE_BYTES
from database import get_db, init_db
from models.rfp import RFP
from services.extractor import extract_requirements
from services.feedback import get_all_feedback, get_feedback_for_rfp, get_feedback_summary, record_feedback
from services.knowledge import get_document, list_documents, search_knowledge, upload_document
from services.fetcher import fetch_url_text
from services.generator import generate_proposal
from services.industry import SUPPORTED_INDUSTRIES, resolve_industry
from services.parser import parse_pdf
from services.profile import evaluate_strategic_fit, load_profile, save_profile
from services.risks import identify_risks
from services.sam_gov import get_opportunity_text, search_opportunities
from services.scoring import score_bid
from services.scoring_config import load_scoring_config, save_scoring_config, validate_scoring_config

app = FastAPI(title="SimpleSeed API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "files"
UPLOAD_DIR.mkdir(exist_ok=True)


class AnalyzeURLRequest(BaseModel):
    url: HttpUrl
    industry: Optional[str] = None


class SAMAnalyzeRequest(BaseModel):
    industry: Optional[str] = None


class FeedbackRequest(BaseModel):
    outcome: str                       # "won" | "lost" | "no_bid"
    result_date: Optional[str] = None  # ISO date "YYYY-MM-DD"; defaults to today
    notes: Optional[str] = None


class ScoringConfigWeights(BaseModel):
    relevance_score:    float
    budget_fit:         float
    requirements_match: float
    completeness:       float


class ScoringConfigRequest(BaseModel):
    weights:              ScoringConfigWeights
    bid_threshold:        float
    strategic_fit_weight: float


class CompanyProfileRequest(BaseModel):
    company_name: Optional[str] = None
    industries: list[str] = []
    capabilities: list[str] = []
    services: list[str] = []
    target_contract_size: dict = {}
    geographies: list[str] = []
    certifications: list[str] = []
    past_performance_keywords: list[str] = []
    preferred_project_types: list[str] = []
    excluded_project_types: list[str] = []
    capacity_constraints: list[str] = []


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/industries")
async def list_industries():
    """Return all supported industry identifiers."""
    from services.industry import INDUSTRY_CONTEXT, DEFAULT_INDUSTRY
    return {
        "default": DEFAULT_INDUSTRY,
        "industries": [
            {"id": k, "label": v["label"]}
            for k, v in INDUSTRY_CONTEXT.items()
        ],
    }


@app.get("/api/profile")
async def get_profile():
    """Return the current company profile. Returns null values when not configured."""
    from services.profile import PROFILE_PATH
    import json as _json
    if not PROFILE_PATH.exists():
        return {"configured": False, "profile": None}
    try:
        raw = _json.loads(PROFILE_PATH.read_text())
        raw.pop("_note", None)
        return {"configured": bool(raw.get("company_name")), "profile": raw}
    except Exception:
        return {"configured": False, "profile": None}


@app.put("/api/profile")
async def update_profile(body: CompanyProfileRequest):
    """Save the company profile. Set company_name to enable strategic fit evaluation."""
    saved = save_profile(body.model_dump())
    return {"configured": bool(saved.get("company_name")), "profile": saved}


@app.post("/api/rfps/{rfp_id}/feedback")
async def add_feedback(
    rfp_id: str, body: FeedbackRequest, db: Session = Depends(get_db)
):
    """Record a win/loss/no_bid outcome for a completed analysis."""
    try:
        fb = record_feedback(
            db=db,
            rfp_id=rfp_id,
            outcome=body.outcome,
            result_date=body.result_date,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.feedback import _serialize
    return _serialize(fb)


@app.get("/api/rfps/{rfp_id}/feedback")
async def list_rfp_feedback(rfp_id: str, db: Session = Depends(get_db)):
    """Return all feedback records for a specific analysis."""
    return get_feedback_for_rfp(db, rfp_id)


@app.get("/api/feedback/summary")
async def feedback_summary(db: Session = Depends(get_db)):
    """
    Return aggregate win/loss metrics and a threshold calibration insight.
    This is the first concrete use of historical feedback data in the MVP.
    Win rates are computed from observed outcomes only — no prediction or ML.
    """
    return get_feedback_summary(db)


@app.get("/api/feedback")
async def list_feedback(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Return recent feedback records across all analyses."""
    return get_all_feedback(db, limit=limit)


# ---------------------------------------------------------------------------
# Knowledge base endpoints
# ---------------------------------------------------------------------------

@app.post("/api/knowledge")
async def upload_knowledge_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF or plain-text file to the internal knowledge base.
    The extracted text is indexed for keyword search via GET /api/knowledge/search.
    """
    file_bytes = await file.read()
    try:
        doc = upload_document(
            db=db,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from services.knowledge import _serialize
    result = _serialize(doc)
    return {
        "success": doc.processing_status == "completed",
        **result,
    }


@app.get("/api/knowledge")
async def list_knowledge_documents(db: Session = Depends(get_db)):
    """List all documents in the knowledge base with their metadata."""
    return list_documents(db)


@app.get("/api/knowledge/{doc_id}")
async def get_knowledge_document(doc_id: str, db: Session = Depends(get_db)):
    """Get metadata for a specific knowledge document."""
    doc = get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/api/scoring-config")
async def get_scoring_config():
    """Return the active scoring configuration (weights, threshold, strategic_fit_weight)."""
    return load_scoring_config()


@app.put("/api/scoring-config")
async def update_scoring_config(body: ScoringConfigRequest):
    """
    Save a new scoring configuration.
    Returns 422 if weights don't sum to 1.0, values are out of range, or fields are missing.
    """
    data = body.model_dump()
    try:
        saved = save_scoring_config(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return saved


@app.post("/api/analyze")
async def analyze_rfp(
    file: UploadFile = File(...),
    industry: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Use rfp_id as the temp filename so retry and delete_rfp can locate the
    # file by ID without storing an extra path in the database.
    rfp_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{rfp_id}.pdf"

    # ── Phase 1: ingest ──────────────────────────────────────────────────────
    # Errors here mean no RFP record was created, so clean up the file
    # immediately and return an HTTP error.  The pipeline has not started.
    try:
        received = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is {MAX_FILE_BYTES // (1024 * 1024)} MB.",
                    )
                f.write(chunk)

        text = parse_pdf(str(file_path))
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF.")
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))

    # ── Phase 2: pipeline ────────────────────────────────────────────────────
    # Hand off to _run_analysis, which owns the file from this point.
    # It will delete file_path on successful completion and preserve it on
    # partial_failure so the retry endpoint has the original PDF available.
    return await _run_analysis(
        text=text, filename=file.filename, industry=industry, db=db,
        rfp_id=rfp_id, file_path=file_path,
    )


@app.get("/api/rfps")
async def list_rfps(db: Session = Depends(get_db)):
    rfps = db.query(RFP).order_by(RFP.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "score": r.score,
            "decision": r.decision,
            "industry": r.industry or "general",
            "pipeline_status": r.pipeline_status or "completed",
            "failed_step": r.failed_step,
            "created_at": r.created_at.isoformat(),
            "summary": _safe_json_load(r.requirements, {}).get("summary", ""),
        }
        for r in rfps
    ]


@app.get("/api/rfps/{rfp_id}")
async def get_rfp(rfp_id: str, db: Session = Depends(get_db)):
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    knowledge_refs = _safe_json_load(rfp.knowledge_refs, [])
    grounding = _safe_json_load(rfp.grounding_report, {})
    evidence_used = grounding.get("evidence_used", [])
    return {
        "id": rfp.id,
        "filename": rfp.filename,
        "industry": rfp.industry or "general",
        "requirements": _safe_json_load(rfp.requirements, {}),
        "risks": _safe_json_load(rfp.risks, []),
        "strategic_fit": _safe_json_load(rfp.strategic_fit, {"status": "unknown"}),
        "proposal": rfp.proposal,
        "score": {
            "score": rfp.score,
            "decision": rfp.decision,
            "breakdown": _safe_json_load(rfp.score_breakdown, {}),
            "reasoning": rfp.reasoning,
        },
        "knowledge_results": knowledge_refs,
        "knowledge_used": [
            {"document_id": r["document_id"], "filename": r["filename"]}
            for r in knowledge_refs
        ],
        "knowledge_status": "used" if knowledge_refs else "no_relevant_documents_found",
        "evidence_used": evidence_used,
        "information_gaps": grounding.get("information_gaps", []),
        "unsupported_claims_avoided": grounding.get("unsupported_claims_avoided", []),
        "grounding_status": (
            "grounded_with_kb" if any(e.get("source") == "internal_document" for e in evidence_used)
            else "rfp_only" if evidence_used
            else "ungrounded"
        ),
        "status": rfp.pipeline_status or "completed",
        "failed_step": rfp.failed_step,
        "completed_steps": _safe_json_load(rfp.completed_steps, []),
        "error": _safe_json_load(rfp.pipeline_error, None),
        "created_at": rfp.created_at.isoformat(),
    }


class RetryRequest(BaseModel):
    retry_from: Optional[str] = None  # defaults to rfp.failed_step when omitted


@app.post("/api/rfps/{rfp_id}/retry")
async def retry_rfp_analysis(
    rfp_id: str,
    body: RetryRequest = Body(default_factory=RetryRequest),
    db: Session = Depends(get_db),
):
    """
    Resume a partial_failure analysis from a specific step without re-uploading
    the document.  Reuses all artifacts already committed for earlier steps.

    - retry_from: which step to restart from. Defaults to the step that failed.
      Valid values: "requirement_extraction", "proposal_generation", "bid_scoring"
    """
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    retry_from = body.retry_from or rfp.failed_step
    if not retry_from:
        raise HTTPException(
            status_code=400,
            detail="No failed_step on record and no retry_from specified in request body.",
        )

    return await _resume_analysis(rfp=rfp, retry_from=retry_from, db=db)


@app.delete("/api/rfps/{rfp_id}")
async def delete_rfp(rfp_id: str, db: Session = Depends(get_db)):
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    file_path = UPLOAD_DIR / f"{rfp_id}.pdf"
    if file_path.exists():
        file_path.unlink()

    db.delete(rfp)
    db.commit()
    return {"message": "Deleted"}


@app.post("/api/analyze-url")
async def analyze_url(body: AnalyzeURLRequest, db: Session = Depends(get_db)):
    url_str = str(body.url)
    try:
        text, source_name = await fetch_url_text(url_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch URL: {e}")

    return await _run_analysis(text=text, filename=source_name, industry=body.industry, db=db)


# ---------------------------------------------------------------------------
# SAM.gov endpoints
# ---------------------------------------------------------------------------

@app.get("/api/sam/search")
async def sam_search(
    q: str = Query(..., description="Keywords to search"),
    naics: str = Query("", description="NAICS code filter"),
    limit: int = Query(10, ge=1, le=25),
    offset: int = Query(0, ge=0),
):
    try:
        result = await search_opportunities(keywords=q, naics_code=naics, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/api/sam/analyze/{notice_id}")
async def sam_analyze(
    notice_id: str,
    body: SAMAnalyzeRequest = Body(default=SAMAnalyzeRequest()),
    db: Session = Depends(get_db),
):
    try:
        text, title = await get_opportunity_text(notice_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _run_analysis(
        text=text, filename=f"SAM.gov — {title}", industry=body.industry, db=db
    )


# ---------------------------------------------------------------------------
# Shared analysis pipeline  (resilient per-step version)
# ---------------------------------------------------------------------------

# Ordered list of pipeline step names — index == position in pipeline.
_PIPELINE_STEPS = ["requirement_extraction", "proposal_generation", "bid_scoring"]


async def _run_analysis(
    text: str,
    filename: str,
    db: Session,
    industry: Optional[str] = None,
    rfp_id: Optional[str] = None,
    file_path: Optional[Path] = None,
) -> dict:
    """
    Start a new analysis from scratch.
    Creates the RFP record immediately, then delegates to _execute_pipeline_steps.

    file_path: if provided (PDF upload path), it is deleted on successful
    pipeline completion and preserved on partial_failure so retry can access
    the original file.  URL and SAM.gov analyses pass None.
    """
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text content could be extracted.")

    resolved_industry = resolve_industry(industry)
    rfp_id = rfp_id or str(uuid.uuid4())

    rfp = RFP(
        id=rfp_id,
        filename=filename,
        original_text=text,           # full text — no truncation
        industry=resolved_industry,
        pipeline_status="processing",
        completed_steps="[]",
        score=0,
        decision="NO BID",
        score_breakdown="{}",
        reasoning="",
        requirements="{}",
        risks="[]",
        strategic_fit="{}",
        knowledge_refs="[]",
        grounding_report="{}",
    )
    try:
        db.add(rfp)
        db.commit()
        db.refresh(rfp)
    except Exception as e:
        # No RFP record was persisted, so retry is impossible.
        # Delete the temp file now — nothing to recover from.
        if file_path:
            file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Database error on record creation: {e}")

    return await _execute_pipeline_steps(
        rfp=rfp, db=db, start_idx=0,
        completed_steps=[],
        requirements={}, risks=[], knowledge_results=[],
        proposal_text="", grounding_report={},
        full_text=text,
        file_path=file_path,
    )


async def _resume_analysis(rfp: RFP, retry_from: str, db: Session) -> dict:
    """
    Resume a partial_failure pipeline from retry_from, reusing already-committed
    artifacts for all steps that completed before it.
    """
    if rfp.pipeline_status != "partial_failure":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot retry: pipeline_status is '{rfp.pipeline_status}'. "
                "Only analyses with status 'partial_failure' can be retried."
            ),
        )

    if retry_from not in _PIPELINE_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid retry_from step '{retry_from}'. Valid steps: {_PIPELINE_STEPS}",
        )

    start_idx = _PIPELINE_STEPS.index(retry_from)
    completed_steps = list(_safe_json_load(rfp.completed_steps, []))

    # Validate that upstream artifacts exist before allowing a mid-pipeline retry
    if start_idx >= 1:
        reqs = _safe_json_load(rfp.requirements, {})
        if not reqs or reqs == {}:
            raise HTTPException(
                status_code=422,
                detail=(
                    "requirement_extraction artifacts are missing or corrupted. "
                    "Retry must start from 'requirement_extraction'."
                ),
            )

    if start_idx >= 2:
        if not rfp.proposal:
            raise HTTPException(
                status_code=422,
                detail=(
                    "proposal_generation artifacts are missing. "
                    "Retry must start from 'proposal_generation' or earlier."
                ),
            )

    # Load persisted artifacts for steps that will be reused
    requirements     = _safe_json_load(rfp.requirements,    {}) if start_idx >= 1 else {}
    risks            = _safe_json_load(rfp.risks,           []) if start_idx >= 1 else []
    knowledge_results = _safe_json_load(rfp.knowledge_refs, []) if start_idx >= 1 else []
    proposal_text    = (rfp.proposal or "")                     if start_idx >= 2 else ""
    grounding_report = _safe_json_load(rfp.grounding_report, {}) if start_idx >= 2 else {}

    reused_steps = _PIPELINE_STEPS[:start_idx]
    rerun_steps  = _PIPELINE_STEPS[start_idx:]

    # Remove the steps being rerun from completed_steps so they get re-appended
    for s in rerun_steps:
        if s in completed_steps:
            completed_steps.remove(s)

    # Reset to processing
    rfp.pipeline_status = "processing"
    rfp.failed_step     = None
    rfp.pipeline_error  = None
    rfp.completed_steps = json.dumps(completed_steps)
    db.commit()

    # Reconstruct the temp file path.  The file was preserved on partial_failure
    # and is named {rfp.id}.pdf (same UUID as the DB record) so we can find it
    # without storing the path explicitly.  _execute_pipeline_steps will delete
    # it on success and leave it in place on another failure.
    retry_file_path = UPLOAD_DIR / f"{rfp.id}.pdf"

    result = await _execute_pipeline_steps(
        rfp=rfp, db=db, start_idx=start_idx,
        completed_steps=completed_steps,
        requirements=requirements, risks=risks, knowledge_results=knowledge_results,
        proposal_text=proposal_text, grounding_report=grounding_report,
        file_path=retry_file_path,
    )

    # Attach retry metadata to the response
    result["retried_from"] = retry_from
    result["reused_steps"] = reused_steps
    result["rerun_steps"]  = rerun_steps
    return result


async def _execute_pipeline_steps(
    rfp: RFP,
    db: Session,
    start_idx: int,
    completed_steps: list,
    requirements: dict,
    risks: list,
    knowledge_results: list,
    proposal_text: str,
    grounding_report: dict,
    full_text: str | None = None,
    file_path: Optional[Path] = None,
) -> dict:
    """
    Run pipeline steps from start_idx onwards.
    For start_idx > 0 the caller has pre-loaded artifacts from earlier steps.
    Each step commits its output immediately; failure returns a partial response.

    file_path: when present, the file is deleted only after all steps succeed
    (pipeline_status == "completed").  On any failure it is left on disk so
    the retry endpoint can re-run the pipeline with the original source file.
    """
    resolved_industry = rfp.industry or "general"
    score_result: dict = {}
    strategic_fit: dict = {"status": "unknown"}

    # ── Step 1: requirement extraction + risks + KB retrieval ────────────────
    if start_idx <= 0:
        text_to_extract = full_text or rfp.original_text or ""
        if not text_to_extract.strip():
            return _record_pipeline_failure(
                db, rfp, completed_steps, "requirement_extraction",
                ValueError("No text available for extraction (original_text is empty)."),
            )
        try:
            requirements = await _llm_with_retry(extract_requirements, text_to_extract)
            risks = await identify_risks(requirements, industry=resolved_industry)

            kb_query_parts = list(requirements.get("keywords") or [])
            if requirements.get("summary"):
                kb_query_parts.append(requirements["summary"])
            kb_query = " ".join(kb_query_parts).strip()
            knowledge_results = search_knowledge(kb_query) if kb_query else []

            rfp.requirements   = json.dumps(requirements)
            rfp.risks          = json.dumps(risks)
            rfp.knowledge_refs = json.dumps(knowledge_results)
            completed_steps.append("requirement_extraction")
            rfp.completed_steps = json.dumps(completed_steps)
            db.commit()
        except Exception as exc:
            return _record_pipeline_failure(db, rfp, completed_steps, "requirement_extraction", exc)

    # ── Step 2: proposal generation ──────────────────────────────────────────
    if start_idx <= 1:
        try:
            proposal_result = await _llm_with_retry(
                generate_proposal,
                requirements,
                industry=resolved_industry,
                knowledge_context=knowledge_results,
            )
            proposal_text    = proposal_result["proposal"]
            grounding_report = {
                "information_gaps":           proposal_result.get("information_gaps", []),
                "unsupported_claims_avoided": proposal_result.get("unsupported_claims_avoided", []),
                "evidence_used":              proposal_result.get("evidence_used", []),
            }

            rfp.proposal          = proposal_text
            rfp.grounding_report  = json.dumps(grounding_report)
            completed_steps.append("proposal_generation")
            rfp.completed_steps   = json.dumps(completed_steps)
            db.commit()
        except Exception as exc:
            return _record_pipeline_failure(db, rfp, completed_steps, "proposal_generation", exc)

    # ── Step 3: bid scoring + strategic fit ──────────────────────────────────
    if start_idx <= 2:
        try:
            scoring_cfg   = load_scoring_config()
            sf_weight     = float(scoring_cfg["strategic_fit_weight"])
            bid_threshold = float(scoring_cfg["bid_threshold"])

            profile       = load_profile()
            strategic_fit = await evaluate_strategic_fit(requirements, profile)
            raw_score     = await score_bid(requirements, industry=resolved_industry)

            if strategic_fit.get("status") == "evaluated":
                fit_score = strategic_fit["score"]
                adjusted  = round(raw_score["score"] * (1 - sf_weight) + fit_score * sf_weight)
                score_result = {
                    **raw_score,
                    "score":    adjusted,
                    "decision": "BID" if adjusted >= bid_threshold else "NO BID",
                    "strategic_fit_weight": sf_weight,
                }
            else:
                score_result = raw_score

            rfp.score           = score_result["score"]
            rfp.decision        = score_result["decision"]
            rfp.score_breakdown = json.dumps(score_result["breakdown"])
            rfp.reasoning       = score_result["reasoning"]
            rfp.strategic_fit   = json.dumps(strategic_fit)
            completed_steps.append("bid_scoring")
            rfp.pipeline_status = "completed"
            rfp.completed_steps = json.dumps(completed_steps)
            db.commit()
            db.refresh(rfp)
        except Exception as exc:
            return _record_pipeline_failure(db, rfp, completed_steps, "bid_scoring", exc)

    # ── All executed steps completed ─────────────────────────────────────────
    # Delete the temp file now that we have a fully committed, successful
    # analysis.  This is the only point in the pipeline where deletion is safe:
    # any earlier exit (via _record_pipeline_failure) preserves the file.
    if file_path:
        file_path.unlink(missing_ok=True)

    knowledge_used = [
        {"document_id": r["document_id"], "filename": r["filename"]}
        for r in knowledge_results
    ]
    knowledge_status = "used" if knowledge_results else "no_relevant_documents_found"
    evidence_used    = grounding_report.get("evidence_used", [])
    grounding_status = (
        "grounded_with_kb" if any(e.get("source") == "internal_document" for e in evidence_used)
        else "rfp_only" if evidence_used
        else "ungrounded"
    )

    return {
        "id":               rfp.id,
        "filename":         rfp.filename,
        "status":           "completed",
        "failed_step":      None,
        "completed_steps":  completed_steps,
        "industry":         resolved_industry,
        "requirements":     requirements,
        "risks":            risks,
        "strategic_fit":    strategic_fit,
        "proposal":         proposal_text,
        "score":            score_result,
        "knowledge_results": knowledge_results,
        "knowledge_used":   knowledge_used,
        "knowledge_status": knowledge_status,
        "evidence_used":    evidence_used,
        "information_gaps": grounding_report.get("information_gaps", []),
        "unsupported_claims_avoided": grounding_report.get("unsupported_claims_avoided", []),
        "grounding_status": grounding_status,
        "error":            None,
        "created_at":       rfp.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

async def _llm_with_retry(fn, *args, max_retries: int = 1, retry_delay: float = 2.0, **kwargs):
    """
    Await fn(*args, **kwargs), retrying once after a delay on any exception.
    Covers transient LLM errors (timeouts, rate limits, connection drops).
    fn must be an async callable — all LLM service functions are async.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)
    raise last_exc  # type: ignore[misc]


def _record_pipeline_failure(
    db: Session,
    rfp: RFP,
    completed_steps: list[str],
    failed_step: str,
    exc: Exception,
) -> dict:
    """
    Persist the failure state and return a structured partial response.
    Already-committed step results remain in the DB and are included in
    the response so the caller receives the maximum useful partial output.
    """
    error = {"type": type(exc).__name__, "message": str(exc)[:500]}
    rfp.pipeline_status = "partial_failure"
    rfp.failed_step = failed_step
    rfp.pipeline_error = json.dumps(error)
    rfp.completed_steps = json.dumps(completed_steps)
    try:
        db.commit()
    except Exception:
        pass  # best-effort — don't shadow the original error

    knowledge_refs = _safe_json_load(rfp.knowledge_refs, [])
    grounding = _safe_json_load(rfp.grounding_report, {})
    evidence_used = grounding.get("evidence_used", [])

    return {
        "id": rfp.id,
        "filename": rfp.filename,
        "status": "partial_failure",
        "failed_step": failed_step,
        "completed_steps": completed_steps,
        "industry": rfp.industry or "general",
        "requirements": _safe_json_load(rfp.requirements, None),
        "risks": _safe_json_load(rfp.risks, None),
        "strategic_fit": None,
        "proposal": rfp.proposal,
        "score": None,
        "knowledge_results": knowledge_refs,
        "knowledge_used": [
            {"document_id": r["document_id"], "filename": r["filename"]}
            for r in knowledge_refs
        ],
        "knowledge_status": "used" if knowledge_refs else "no_relevant_documents_found",
        "evidence_used": evidence_used,
        "information_gaps": grounding.get("information_gaps", []),
        "unsupported_claims_avoided": grounding.get("unsupported_claims_avoided", []),
        "grounding_status": "ungrounded",
        "error": error,
        "created_at": rfp.created_at.isoformat() if rfp.created_at else None,
    }


def _safe_json_load(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
