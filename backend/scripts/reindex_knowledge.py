#!/usr/bin/env python
"""
CLI script: chunk and embed knowledge base documents for semantic search.

Usage (run from the backend/ directory):
    python scripts/reindex_knowledge.py              # index only un-indexed docs
    python scripts/reindex_knowledge.py --all        # force re-index every doc
    python scripts/reindex_knowledge.py --doc <id>   # index one specific document

Prerequisites:
    OPENAI_API_KEY must be set (or EMBEDDING_MODEL if using a different provider).
    Without it the script still runs but stores null embeddings (no-op for search).

Exit codes:
    0 — all documents indexed successfully (or no documents needed indexing)
    1 — one or more documents failed to index
"""
import argparse
import sys
from pathlib import Path

# Ensure backend/ is on the Python path when called as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub modules that may be absent in minimal environments
import importlib
for _mod in ["pdfplumber", "services.parser", "pytesseract", "pdf2image"]:
    try:
        importlib.import_module(_mod)
    except ImportError:
        import types
        sys.modules.setdefault(_mod, types.ModuleType(_mod))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reindex knowledge base documents for semantic search."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Force re-index all completed documents (including already-indexed ones).",
    )
    parser.add_argument(
        "--doc",
        metavar="DOC_ID",
        default=None,
        help="Reindex a single document by its ID.",
    )
    args = parser.parse_args()

    from database import SessionLocal, init_db
    from models.knowledge_document import KnowledgeDocument
    from services.knowledge import index_document_chunks

    init_db()
    db = SessionLocal()

    failed = 0
    try:
        q = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.processing_status == "completed"
        )
        if args.doc:
            q = q.filter(KnowledgeDocument.id == args.doc)
        elif not args.all:
            q = q.filter(KnowledgeDocument.embedding_status != "completed")

        docs = q.order_by(KnowledgeDocument.uploaded_at).all()

        if not docs:
            print("No documents require indexing.")
            return 0

        print(f"Indexing {len(docs)} document(s)...")
        for doc in docs:
            print(f"  [{doc.id}] {doc.filename} ...", end=" ", flush=True)
            try:
                index_document_chunks(doc.id, db)
                db.refresh(doc)
                status = getattr(doc, "embedding_status", "?")
                chunks = getattr(doc, "chunk_count", 0)
                print(f"{status} ({chunks} chunks)")
                if status == "failed":
                    failed += 1
            except Exception as exc:
                print(f"ERROR: {exc}")
                failed += 1

        print(
            f"\nDone. {len(docs) - failed}/{len(docs)} documents indexed successfully."
        )
        return 1 if failed else 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
