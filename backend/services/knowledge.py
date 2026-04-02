"""
Knowledge base service.
MVP: keyword-based text search over local documents.
Future: semantic search with embeddings + vector DB.
"""
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def search_knowledge(query: str, top_k: int = 3) -> list[dict]:
    """Return top_k documents most relevant to query."""
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    query_words = set(query.lower().split())
    results = []

    for doc_path in KNOWLEDGE_DIR.glob("*.txt"):
        content = doc_path.read_text(encoding="utf-8", errors="ignore")
        overlap = len(query_words & set(content.lower().split()))
        if overlap > 0:
            results.append({
                "filename": doc_path.name,
                "snippet": content[:500],
                "relevance": overlap,
            })

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results[:top_k]


def add_document(filename: str, content: str) -> None:
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    (KNOWLEDGE_DIR / filename).write_text(content, encoding="utf-8")
