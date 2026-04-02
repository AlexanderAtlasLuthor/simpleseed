import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None

# Documents within this limit are sent in a single LLM call.
# 120k chars ≈ 30k tokens — well within Haiku's 200k-token context window.
# Covers any RFP up to ~60 dense pages.
_SINGLE_PASS_LIMIT = 120_000

# Chunk parameters for map-reduce on very large documents.
_CHUNK_SIZE = 40_000   # chars per chunk
_CHUNK_OVERLAP = 300   # overlap to avoid cutting mid-sentence at boundaries


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
    """
    if len(text) <= _SINGLE_PASS_LIMIT:
        return _extract_single(text)
    return _extract_chunked(text)


# ---------------------------------------------------------------------------
# Single-pass extraction (one LLM call, full text)
# ---------------------------------------------------------------------------

def _extract_single(text: str) -> dict:
    prompt = f"""Analyze this RFP (Request for Proposal) and extract structured information.

Return a JSON object with exactly these fields:
- "summary": string — 2-3 sentence overview of what is being requested
- "client": string or null — organization name if mentioned
- "deadline": string or null — submission deadline if mentioned
- "budget": string or null — budget range if mentioned
- "requirements": array of objects — each requirement with two independent classifications:
  {{
    "text": string — the requirement exactly as stated or closely paraphrased,
    "category": "mandatory" | "optional" | "unclear",
    "reason": string — brief signal justifying the category (e.g. "uses 'must'"),
    "type": "technical" | "administrative" | "unclear",
    "type_reason": string — brief justification for the type classification
  }}
  Category classification rules:
  - "mandatory": language like must, shall, will, required, mandatory, is required to, needs to
  - "optional": language like should, preferred, desirable, nice to have, may, could, ideally, if possible, encouraged to
  - "unclear" (category): no explicit qualifier, generic or implied statement, ambiguous phrasing
  Type classification rules:
  - "technical": relates to technology, architecture, systems, APIs, performance, security, data, infrastructure, integration, testing, or software development
  - "administrative": relates to compliance, legal terms, certifications, deadlines, documentation, reporting, vendor qualifications, insurance, contracts, or personnel credentials
  - "unclear" (type): spans both domains or contains insufficient context to decide
- "evaluation_criteria": array of strings — how proposals will be evaluated
- "deliverables": array of strings — expected deliverables
- "keywords": array of strings — 5-10 important keywords/topics

RFP TEXT:
{text}

Return only valid JSON. No markdown, no extra text."""

    message = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    content = message.content[0].text

    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception:
        return _empty_result(summary=content[:500])


# ---------------------------------------------------------------------------
# Map-reduce for very large documents (> 120k chars)
# ---------------------------------------------------------------------------

def _extract_chunked(text: str) -> dict:
    chunks = _split_into_chunks(text)
    partials = [_extract_single(chunk) for chunk in chunks]
    return _merge_extractions(partials)


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
        start = end - _CHUNK_OVERLAP  # overlap to preserve cross-boundary context

    return chunks


def _merge_extractions(partials: list[dict]) -> dict:
    """
    Merge N partial extractions into one.
    - Scalar fields (client, deadline, budget): first non-null value wins.
    - summary: taken from the first chunk (contains document intro).
    - Array fields: union, deduplicating by normalized text.
    """
    merged = _empty_result(summary=partials[0].get("summary", "") if partials else "")

    seen: dict[str, set] = {
        "requirements": set(),
        "evaluation_criteria": set(),
        "deliverables": set(),
        "keywords": set(),
    }

    for partial in partials:
        if not merged["client"] and partial.get("client"):
            merged["client"] = partial["client"]
        if not merged["deadline"] and partial.get("deadline"):
            merged["deadline"] = partial["deadline"]
        if not merged["budget"] and partial.get("budget"):
            merged["budget"] = partial["budget"]

        for field in ("requirements", "evaluation_criteria", "deliverables", "keywords"):
            for item in partial.get(field) or []:
                # requirements items are dicts {text, category, reason}; others are strings
                key = (item.get("text") if isinstance(item, dict) else item)
                key = (key or "").lower().strip()
                if key and key not in seen[field]:
                    seen[field].add(key)
                    merged[field].append(item)

    return merged


def _empty_result(summary: str = "") -> dict:
    return {
        "summary": summary,
        "client": None,
        "deadline": None,
        "budget": None,
        "requirements": [],
        "evaluation_criteria": [],
        "deliverables": [],
        "keywords": [],
    }
