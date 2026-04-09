"""
Document chunking for semantic retrieval.

Strategy
--------
1. Normalise whitespace (collapse 3+ newlines → 2).
2. Split on paragraph boundaries (double-newline).
3. Accumulate paragraphs into a buffer until CHUNK_MAX_CHARS is reached.
4. When a paragraph alone exceeds CHUNK_MAX_CHARS, split it further:
   a. Try sentence boundaries first (regex on [.!?]).
   b. Fall back to hard character slicing for extremely long sentences.
5. When flushing the buffer, carry CHUNK_OVERLAP_CHARS of the previous
   buffer into the start of the next chunk.  This prevents information loss
   at paragraph boundaries.
6. Drop any resulting chunk shorter than CHUNK_MIN_CHARS.

Chunk size targets
------------------
  Target:  ~800 chars (~200 tokens with typical prose density)
  Max:    2 000 chars (~500 tokens) — keeps specificity high for retrieval
  Min:      100 chars — filters page numbers, stray headings, etc.
  Overlap:  200 chars between adjacent chunks

Why this approach?
------------------
  • 200–500 tokens per chunk is the widely-validated sweet spot for embedding
    retrieval: large enough for context, small enough for specificity.
  • Paragraph-first splitting preserves natural semantic units; sentence
    splitting only kicks in when a paragraph is unusually long.
  • Overlap prevents retrieval gaps when a relevant passage straddles two
    natural boundaries.
  • No external NLP dependencies — pure Python, works in any environment.
"""

import hashlib
import re
import uuid
from typing import Iterator

# ── Tuneable constants ────────────────────────────────────────────────────────
CHUNK_TARGET_CHARS = 800
CHUNK_MAX_CHARS    = 2_000
CHUNK_MIN_CHARS    = 100
CHUNK_OVERLAP_CHARS = 200


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_document(text: str) -> list[dict]:
    """
    Split *text* into overlapping chunks suitable for embedding.

    Returns a list of dicts (one per retained chunk):
        {
            "chunk_index":   int,   # 0-based, re-indexed after filtering
            "text":          str,
            "char_count":    int,
            "content_hash":  str,   # SHA-256(text) — for idempotency
            "chunk_type":    str,   # "text" | "header"
        }
    """
    if not text or not text.strip():
        return []

    raw_chunks = list(_split_text(text))

    result = []
    for raw in raw_chunks:
        stripped = raw.strip()
        if len(stripped) < CHUNK_MIN_CHARS:
            continue
        result.append({
            "chunk_index":  len(result),          # will be re-assigned below
            "text":         stripped,
            "char_count":   len(stripped),
            "content_hash": _sha256(stripped),
            "chunk_type":   _classify_chunk(stripped),
        })

    # Compact the indices after filtering
    for i, chunk in enumerate(result):
        chunk["chunk_index"] = i

    return result


# ── Splitting helpers ─────────────────────────────────────────────────────────

def _split_text(text: str) -> Iterator[str]:
    """
    Primary split: paragraph → sentence → character.
    Yields raw chunk strings (may be short; caller filters).
    """
    text = re.sub(r"\n{3,}", "\n\n", text)          # normalise whitespace
    paragraphs = text.split("\n\n")

    buffer = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # A single paragraph that's already too large → sub-split it
        if len(para) > CHUNK_MAX_CHARS:
            if buffer:
                yield buffer
                buffer = ""
            yield from _split_large_block(para)
            continue

        combined = (buffer + "\n\n" + para).strip() if buffer else para

        if len(combined) > CHUNK_MAX_CHARS and buffer:
            # Flush and start fresh with overlap
            yield buffer
            overlap = buffer[-CHUNK_OVERLAP_CHARS:] if len(buffer) > CHUNK_OVERLAP_CHARS else buffer
            buffer = (overlap + "\n\n" + para).strip()
        else:
            buffer = combined

    if buffer.strip():
        yield buffer


def _split_large_block(text: str) -> Iterator[str]:
    """
    Split a block that exceeds CHUNK_MAX_CHARS using sentence boundaries.
    Sentences longer than CHUNK_MAX_CHARS are hard-sliced as a last resort.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)

    buffer = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        # Sentence that's already huge → hard slice
        if len(sent) > CHUNK_MAX_CHARS:
            if buffer:
                yield buffer
                buffer = ""
            yield from _slice_by_chars(sent)
            continue

        combined = (buffer + " " + sent).strip() if buffer else sent
        if len(combined) > CHUNK_MAX_CHARS and buffer:
            yield buffer
            overlap = buffer[-CHUNK_OVERLAP_CHARS:] if len(buffer) > CHUNK_OVERLAP_CHARS else buffer
            buffer = (overlap + " " + sent).strip()
        else:
            buffer = combined

    if buffer.strip():
        yield buffer


def _slice_by_chars(text: str) -> Iterator[str]:
    """Last-resort: hard-slice into CHUNK_MAX_CHARS windows with overlap."""
    start = 0
    while start < len(text):
        end = min(start + CHUNK_MAX_CHARS, len(text))
        yield text[start:end]
        if end == len(text):
            break
        next_start = end - CHUNK_OVERLAP_CHARS
        start = next_start if next_start > start else end  # guard against infinite loop


# ── Metadata helpers ──────────────────────────────────────────────────────────

def _classify_chunk(text: str) -> str:
    """
    Heuristic: classify a chunk as 'header' or 'text'.
    A short first line that looks like a heading is labelled 'header'.
    """
    first_line = text.split("\n")[0].strip()
    if (
        len(first_line) < 80
        and len(text.split("\n")) <= 3
        and (first_line.isupper() or re.match(r"^[A-Z0-9][A-Z0-9 ./\-:]+$", first_line))
    ):
        return "header"
    return "text"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
