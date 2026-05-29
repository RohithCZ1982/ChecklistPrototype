"""Unified search engine combining semantic + keyword search."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.database import get_document, keyword_search_chunks, list_documents
from modules.extractor import answer_question
from modules.vector_store import semantic_search
from utils.helpers import truncate


def global_search(
    query: str,
    doc_ids: Optional[List[str]] = None,
    top_k: int = 10,
    search_mode: str = "both",  # 'semantic' | 'keyword' | 'both'
    min_confidence: float = 0.2,
) -> List[Dict]:
    """
    Execute a unified search and return enriched result dicts:
      {chunk_id, document_id, filename, text, page_number,
       confidence, source, snippet}
    """
    hits_map: Dict[str, Dict] = {}

    # ── Semantic ──────────────────────────────────────────────────────────────
    if search_mode in ("semantic", "both"):
        sem_hits = semantic_search(
            query, top_k=top_k, doc_ids=doc_ids, threshold=min_confidence
        )
        for h in sem_hits:
            hits_map[h["chunk_id"]] = {**h, "source": "semantic"}

    # ── Keyword ───────────────────────────────────────────────────────────────
    if search_mode in ("keyword", "both"):
        kw_rows = keyword_search_chunks(query, doc_ids=doc_ids, limit=top_k)
        for row in kw_rows:
            cid = row["id"]
            if cid not in hits_map:
                hits_map[cid] = {
                    "chunk_id": cid,
                    "document_id": row["document_id"],
                    "text": row["text"],
                    "page_number": row.get("page_number", 1),
                    "confidence": 0.5,
                    "source": "keyword",
                }

    results = list(hits_map.values())

    # Enrich with document filename
    doc_cache: Dict[str, Optional[Dict]] = {}
    for r in results:
        did = r["document_id"]
        if did not in doc_cache:
            doc_cache[did] = get_document(did)
        doc = doc_cache[did]
        r["filename"] = doc["filename"] if doc else "Unknown"
        r["doc_title"] = doc.get("title") or doc["filename"] if doc else ""
        r["snippet"] = _highlight_snippet(r["text"], query)

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:top_k]


def rag_answer(
    question: str,
    doc_ids: Optional[List[str]] = None,
    top_k: int = 6,
) -> Dict[str, Any]:
    """
    Retrieve relevant chunks, then synthesize an answer with the LLM.
    Returns {answer, sources}.
    """
    hits = global_search(question, doc_ids=doc_ids, top_k=top_k, search_mode="semantic")
    context_chunks = [h["text"] for h in hits]
    titles = list({h["filename"] for h in hits})
    answer = answer_question(question, context_chunks, document_titles=titles)
    return {
        "answer": answer,
        "sources": hits,
    }


def document_similarity_matrix(doc_ids: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Compute pairwise Jaccard-based similarity between documents.
    Returns nested dict matrix[doc_id_a][doc_id_b] = score.
    """
    from modules.database import get_chunks
    from modules.document_processor import detect_similarity

    texts: Dict[str, str] = {}
    for did in doc_ids:
        chunks = get_chunks(did)
        texts[did] = " ".join(c["text"] for c in chunks[:20])

    matrix: Dict[str, Dict[str, float]] = {}
    for i, a in enumerate(doc_ids):
        matrix[a] = {}
        for b in doc_ids:
            if a == b:
                matrix[a][b] = 1.0
            elif b in matrix and a in matrix[b]:
                matrix[a][b] = matrix[b][a]
            else:
                matrix[a][b] = round(detect_similarity(texts.get(a, ""), texts.get(b, "")), 3)

    return matrix


def _highlight_snippet(text: str, query: str, window: int = 300) -> str:
    """Return a short snippet with the query term near the center."""
    import re
    lower_text = text.lower()
    lower_q = query.lower().split()[0] if query.split() else ""
    idx = lower_text.find(lower_q)
    if idx == -1:
        return truncate(text, window)
    start = max(0, idx - window // 2)
    end = min(len(text), idx + window // 2)
    snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    return snippet
