import json
import logging
import os
import anthropic
from dotenv import load_dotenv
from settings import llm_model

load_dotenv()

logger = logging.getLogger(__name__)
_client = None

# Documents within this limit are sent in a single LLM call.
# 120k chars ≈ 30k tokens — well within Haiku's 200k-token context window.
# Covers any RFP up to ~60 dense pages.
_SINGLE_PASS_LIMIT = 120_000

# Chunk parameters for map-reduce on very large documents.
_CHUNK_SIZE = 40_000   # chars per chunk
_CHUNK_OVERLAP = 300   # overlap to avoid cutting mid-sentence at boundaries

# Valid values for status / confidence fields.
_VALID_STATUSES = {"complete", "partial", "ambiguous", "failed"}
_VALID_CONFIDENCES = {"high", "medium", "low"}


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def extract_requirements(text: str) -> dict:
    """
    Extract structured requirements from RFP text.

    Strategy:
    - text ≤ 120,000 chars → single LLM call with full text
    - text  > 120,000 chars → map-reduce: chunk → extract each → merge

    Always returns a dict with extraction_status, confidence, and notes
    so callers can distinguish complete / partial / ambiguous / failed.
    """
    if len(text) <= _SINGLE_PASS_LIMIT:
        logger.debug("Extraction strategy=single_pass text_len=%d", len(text))
        return _extract_single(text)
    logger.debug(
        "Extraction strategy=chunked text_len=%d (exceeds single-pass limit of %d)",
        len(text), _SINGLE_PASS_LIMIT,
    )
    return _extract_chunked(text)


# ---------------------------------------------------------------------------
# Prompt (shared by single-pass and each chunk in map-reduce)
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """Analyze this document and extract structured information. \
The document may be a well-formed RFP, a partial draft, or something ambiguous.

Return a JSON object with exactly these fields:

- "summary": string — 2-3 sentence overview of what is being requested. \
  If the document is unclear, describe what it appears to be.

- "client": string or null — organization issuing the RFP, if identifiable
- "deadline": string or null — submission deadline, if stated
- "budget": string or null — budget or price ceiling, if stated

- "requirements": array of objects — ONLY requirements that are CLEARLY and EXPLICITLY stated:
  {{
    "text": string — the requirement as stated or closely paraphrased,
    "category": "mandatory" | "optional" | "unclear",
    "reason": string — brief signal justifying the category (e.g. "uses 'must'"),
    "type": "technical" | "administrative" | "unclear",
    "type_reason": string — brief justification for the type classification
  }}
  Category rules: mandatory (must/shall/required/will), optional (should/preferred/nice to have/may/could),
  unclear (no explicit qualifier or ambiguous phrasing).
  Type rules: technical (technology/architecture/APIs/performance/security/data/infrastructure/integration/testing),
  administrative (compliance/legal/certifications/deadlines/documentation/reporting/vendor qualifications/insurance).

- "unclear_requirements": array of objects — items that MIGHT be requirements but are ambiguous,
  vague, implied, or lack sufficient context to classify with confidence. DO NOT discard these.
  {{
    "text": string — the unclear item as stated or paraphrased,
    "reason": string — why this is unclear (e.g. "no explicit obligation language", \
"references a prior document not included", "context is missing")
  }}

- "missing_information": array of strings — key RFP elements that are EXPECTED but NOT FOUND.
  Common examples: "Submission deadline", "Budget or price ceiling", "Evaluation criteria",
  "Required deliverables", "Vendor qualifications", "Technical scope detail", "Contract type"

- "extraction_status": classify the overall extraction quality as one of:
  - "complete" — well-structured RFP with clear requirements and most key fields present
  - "partial" — some requirements found but document is incomplete or missing key sections
  - "ambiguous" — document appears RFP-related but requirements are unclear or poorly structured
  - "failed" — document does not appear to contain RFP content, or is unreadable / garbled

- "confidence": "high" | "medium" | "low" — your overall confidence in the extraction accuracy

- "notes": string or null — any important caveats about the document quality or extraction limitations

- "evaluation_criteria": array of strings — how proposals will be evaluated
- "deliverables": array of strings — expected deliverables
- "keywords": array of strings — 5-10 important keywords/topics

CRITICAL RULES:
- If you find requirements you are not confident about, put them in "unclear_requirements" — never discard them.
- Do NOT invent requirements that are not present in the document.
- If requirements and unclear_requirements are both empty despite the document having content,
  set extraction_status to "ambiguous" and explain in "notes".
- If the document is empty, garbled, or clearly not an RFP, set extraction_status to "failed".

DOCUMENT TEXT:
{text}

Return only valid JSON. No markdown, no extra text."""


# ---------------------------------------------------------------------------
# Single-pass extraction (one LLM call, full text)
# ---------------------------------------------------------------------------

def _extract_single(text: str) -> dict:
    prompt = _EXTRACTION_PROMPT.format(text=text)

    logger.debug("LLM call extract_requirements model=%s", llm_model)
    message = get_client().messages.create(
        model=llm_model,
        max_tokens=2500,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    content = message.content[0].text

    try:
        cleaned = _strip_markdown_fences(content)
        result = json.loads(cleaned)
        enriched = _enrich_result(result)
        logger.debug(
            "Extraction parse succeeded status=%s confidence=%s "
            "requirements=%d unclear=%d",
            enriched.get("extraction_status"), enriched.get("confidence"),
            len(enriched.get("requirements", [])),
            len(enriched.get("unclear_requirements", [])),
        )
        return enriched
    except Exception:
        # First parse failed — attempt a rescue extraction before giving up.
        logger.warning("Extraction primary parse failed — attempting rescue extraction")
        return _rescue_extract(text, content)


def _rescue_extract(text: str, failed_content: str) -> dict:
    """
    Second-chance extraction when the primary parse fails.
    Uses a simpler prompt focused on recovering partial signal.
    Returns a result with extraction_status="failed" if this also fails.
    """
    rescue_prompt = f"""The following document could not be parsed as structured JSON. \
Extract whatever information you can from it.

Return a JSON object with these fields only:
{{
  "summary": string or null,
  "notes": string — describe what the document appears to contain and why parsing was difficult,
  "unclear_requirements": [
    {{"text": string, "reason": "could not be classified with certainty"}}
  ],
  "missing_information": [string],
  "extraction_status": "ambiguous" | "failed",
  "confidence": "low"
}}

DOCUMENT (first 8000 chars):
{text[:8000]}

Return only valid JSON. No markdown."""

    try:
        message = get_client().messages.create(
            model=llm_model,
            max_tokens=800,
            temperature=0,
            messages=[{"role": "user", "content": rescue_prompt}],
        )
        cleaned = _strip_markdown_fences(message.content[0].text)
        partial = json.loads(cleaned)

        result = _empty_result(summary=partial.get("summary") or failed_content[:300])
        result["unclear_requirements"] = partial.get("unclear_requirements") or []
        result["missing_information"] = partial.get("missing_information") or []
        result["notes"] = partial.get("notes") or "Primary extraction failed; partial recovery attempted."
        result["extraction_status"] = partial.get("extraction_status", "failed")
        result["confidence"] = "low"
        return result

    except Exception:
        # Both passes failed — return an informative failed result, never silent empty.
        logger.error("Extraction rescue parse also failed — returning status=failed")
        result = _empty_result(summary=failed_content[:300])
        result["extraction_status"] = "failed"
        result["confidence"] = "low"
        result["notes"] = (
            "Extraction failed: the LLM response could not be parsed as JSON. "
            "The document may be unreadable, too short, or not an RFP."
        )
        return result


# ---------------------------------------------------------------------------
# Map-reduce for very large documents (> 120k chars)
# ---------------------------------------------------------------------------

def _extract_chunked(text: str) -> dict:
    chunks = _split_into_chunks(text)
    logger.debug("Chunked extraction chunks=%d total_text_len=%d", len(chunks), len(text))
    partials = [_extract_single(chunk) for chunk in chunks]
    merged = _merge_extractions(partials)
    logger.debug(
        "Chunked extraction merge completed status=%s requirements=%d",
        merged.get("extraction_status"), len(merged.get("requirements", [])),
    )
    return merged


def _split_into_chunks(text: str) -> list[str]:
    """Split text into overlapping chunks, breaking at newlines when possible."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))

        # If not at the end, try to break at the last newline within a 500-char window
        if end < len(text):
            newline = text.rfind("\n", end - 500, end)
            if newline > start:
                end = newline

        chunks.append(text[start:end])
        next_start = end - _CHUNK_OVERLAP
        # Guard: always advance forward to prevent infinite loop
        start = max(next_start, start + 1) if next_start > start else end

    return chunks


def _merge_extractions(partials: list[dict]) -> dict:
    """
    Merge N partial extractions into one.
    - Scalar fields (client, deadline, budget): first non-null value wins.
    - summary: taken from the first chunk (contains document intro).
    - Array fields: union, deduplicating by normalized text.
    - extraction_status: escalates to the most severe status seen.
    - confidence: takes the lowest confidence seen.
    - notes: concatenates non-empty notes from each chunk.
    """
    merged = _empty_result(summary=partials[0].get("summary", "") if partials else "")

    seen: dict[str, set] = {
        "requirements": set(),
        "unclear_requirements": set(),
        "evaluation_criteria": set(),
        "deliverables": set(),
        "keywords": set(),
        "missing_information": set(),
    }

    status_priority = {"complete": 0, "partial": 1, "ambiguous": 2, "failed": 3}
    worst_status = "complete"
    worst_confidence = "high"
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    notes_parts: list[str] = []

    for partial in partials:
        if not merged["client"] and partial.get("client"):
            merged["client"] = partial["client"]
        if not merged["deadline"] and partial.get("deadline"):
            merged["deadline"] = partial["deadline"]
        if not merged["budget"] and partial.get("budget"):
            merged["budget"] = partial["budget"]

        for field in ("requirements", "evaluation_criteria", "deliverables", "keywords"):
            for item in partial.get(field) or []:
                key = (item.get("text") if isinstance(item, dict) else item)
                key = (key or "").lower().strip()
                if key and key not in seen[field]:
                    seen[field].add(key)
                    merged[field].append(item)

        for item in partial.get("unclear_requirements") or []:
            key = (item.get("text") if isinstance(item, dict) else str(item)).lower().strip()
            if key and key not in seen["unclear_requirements"]:
                seen["unclear_requirements"].add(key)
                merged["unclear_requirements"].append(item)

        for item in partial.get("missing_information") or []:
            key = str(item).lower().strip()
            if key and key not in seen["missing_information"]:
                seen["missing_information"].add(key)
                merged["missing_information"].append(item)

        # Track worst status and confidence across chunks
        chunk_status = partial.get("extraction_status", "partial")
        if status_priority.get(chunk_status, 1) > status_priority.get(worst_status, 0):
            worst_status = chunk_status

        chunk_confidence = partial.get("confidence", "medium")
        if confidence_order.get(chunk_confidence, 1) > confidence_order.get(worst_confidence, 0):
            worst_confidence = chunk_confidence

        if partial.get("notes"):
            notes_parts.append(partial["notes"])

    merged["extraction_status"] = worst_status
    merged["confidence"] = worst_confidence
    merged["notes"] = " | ".join(notes_parts) if notes_parts else None

    return _enrich_result(merged)


# ---------------------------------------------------------------------------
# Post-processing: validate, normalize, override status when needed
# ---------------------------------------------------------------------------

def _enrich_result(result: dict) -> dict:
    """
    Ensure all new fields are present and extraction_status reflects reality.
    Overrides optimistic LLM self-assessments when the evidence says otherwise.
    Never removes extracted content — only adds missing fields and corrects status.
    """
    # Ensure every new field always exists
    result.setdefault("unclear_requirements", [])
    result.setdefault("missing_information", [])
    result.setdefault("notes", None)
    result.setdefault("confidence", "medium")
    result.setdefault("extraction_status", "partial")

    # Coerce invalid values from the LLM to safe defaults
    if result["extraction_status"] not in _VALID_STATUSES:
        result["extraction_status"] = "partial"
    if result["confidence"] not in _VALID_CONFIDENCES:
        result["confidence"] = "medium"

    has_requirements = bool(result.get("requirements"))
    has_unclear = bool(result.get("unclear_requirements"))
    has_summary = bool((result.get("summary") or "").strip())

    # Override status when the extracted content contradicts the LLM's claim
    if not has_requirements and not has_unclear and not has_summary:
        result["extraction_status"] = "failed"
        result["confidence"] = "low"
        if not result["notes"]:
            result["notes"] = (
                "No structured information could be extracted. "
                "The document may be empty, too short, or not an RFP."
            )
    elif not has_requirements and not has_unclear:
        # Has a summary but literally nothing else — definitely not "complete"
        if result["extraction_status"] == "complete":
            result["extraction_status"] = "ambiguous"
        if result["confidence"] == "high":
            result["confidence"] = "medium"
        if not result["notes"]:
            result["notes"] = (
                "A summary was extracted but no individual requirements could be identified. "
                "The document may be a high-level overview rather than a detailed RFP."
            )
    elif not has_requirements and has_unclear:
        # Items found but none classifiable as definitive requirements
        if result["extraction_status"] == "complete":
            result["extraction_status"] = "ambiguous"
        if result["confidence"] == "high":
            result["confidence"] = "medium"

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_markdown_fences(content: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    if "```json" in content:
        return content.split("```json")[1].split("```")[0].strip()
    if "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    return content.strip()


def _empty_result(summary: str = "") -> dict:
    return {
        "summary": summary,
        "client": None,
        "deadline": None,
        "budget": None,
        "requirements": [],
        "unclear_requirements": [],
        "evaluation_criteria": [],
        "deliverables": [],
        "keywords": [],
        "missing_information": [],
        "extraction_status": "partial",
        "confidence": "medium",
        "notes": None,
    }
