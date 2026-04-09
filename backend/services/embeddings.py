"""
Embedding service.

Default provider : OpenAI text-embedding-3-small (1536 dimensions)
                   Called directly via httpx — no openai SDK required.
Fallback         : If OPENAI_API_KEY is absent, every call returns None
                   and the retrieval layer falls back to keyword matching.

Configuration (environment variables)
--------------------------------------
  OPENAI_API_KEY        required for embeddings
  EMBEDDING_MODEL       default: text-embedding-3-small
  EMBEDDING_BATCH_SIZE  chunks per API call, default: 100

Cost tracking
-------------
  embed_texts() logs the number of texts embedded each call so operators can
  monitor embedding volume in application logs without a full billing layer.

Idempotency note
----------------
  Callers that want to skip re-embedding identical content should compare the
  chunk's content_hash against the stored hash before calling embed_texts().
  This module does NOT deduplicate — that logic lives in knowledge.py.
"""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL      = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMS       = 1536          # text-embedding-3-small output dimension
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
_MAX_RETRIES         = 3
_RETRY_BASE_DELAY    = 1.0           # seconds; doubles each attempt


# ── Public API ────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """
    Generate embeddings for a list of texts.

    Returns a parallel list of float arrays.  Any position whose embedding
    failed is None.  Never raises — failures are logged and nulled.

    Batches the input at EMBEDDING_BATCH_SIZE items per API request.
    """
    if not texts:
        return []

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY not configured — embeddings disabled. "
            "Knowledge retrieval will use keyword fallback."
        )
        return [None] * len(texts)

    results: list[Optional[list[float]]] = [None] * len(texts)

    batch_count = 0
    for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
        batch_embeddings = _embed_batch_with_retry(batch, api_key)
        for j, emb in enumerate(batch_embeddings):
            results[batch_start + j] = emb
        batch_count += 1

    embedded = sum(1 for r in results if r is not None)
    logger.info(
        "embed_texts: %d/%d texts embedded in %d batch(es) via %s",
        embedded, len(texts), batch_count, EMBEDDING_MODEL,
    )
    return results


def embed_query(text: str) -> Optional[list[float]]:
    """Embed a single query string.  Returns None if unavailable."""
    results = embed_texts([text])
    return results[0] if results else None


def embeddings_available() -> bool:
    """Return True if the embedding provider is configured."""
    return bool(os.getenv("OPENAI_API_KEY"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _embed_batch_with_retry(
    texts: list[str],
    api_key: str,
) -> list[Optional[list[float]]]:
    """
    POST to the OpenAI embeddings endpoint with exponential-backoff retry.

    Returns a list of float arrays (same length as texts); positions that
    permanently fail are None.
    """
    import httpx  # already in requirements.txt

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":           EMBEDDING_MODEL,
        "input":           texts,
        "encoding_format": "float",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            # Sort by index to guarantee alignment with input order
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]

        except Exception as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Embedding batch failed (attempt %d/%d, %d texts): %s — retry in %.1fs",
                attempt + 1, _MAX_RETRIES, len(texts), exc, delay,
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(delay)

    logger.error(
        "Embedding batch permanently failed after %d attempts (%d texts): %s",
        _MAX_RETRIES, len(texts), last_exc,
    )
    return [None] * len(texts)
