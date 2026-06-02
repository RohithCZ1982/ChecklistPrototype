"""ChromaDB vector store wrapper with sentence-transformer embeddings."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import streamlit as st

from config import CHROMA_DIR, EMBEDDING_MODEL, SIMILARITY_THRESHOLD, TOP_K_RESULTS


# ─── Embedding model (cached per process) ────────────────────────────────────

@st.cache_resource(show_spinner="Loading embedding model…")
def _load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts."""
    model = _load_embedding_model()
    return model.encode(texts, show_progress_bar=False, batch_size=32).tolist()


def embed_one(text: str) -> List[float]:
    return embed([text])[0]


# ─── ChromaDB client (cached per process) ────────────────────────────────────

@st.cache_resource(show_spinner="Connecting to vector store…")
def _get_chroma_client():
    import chromadb
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _get_collection():
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name="doc_chunks",
        metadata={"hnsw:space": "cosine"},
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def index_chunks(
    chunk_ids: List[str],
    texts: List[str],
    doc_id: str,
    extra_meta: Optional[List[Dict]] = None,
) -> None:
    """Embed and upsert chunks into ChromaDB."""
    if not texts:
        return

    collection = _get_collection()
    embeddings = embed(texts)

    metadatas = []
    for i, text in enumerate(texts):
        meta: Dict[str, Any] = {"document_id": doc_id, "chunk_index": i}
        if extra_meta and i < len(extra_meta):
            # ChromaDB metadata values must be str/int/float/bool
            for k, v in extra_meta[i].items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
        metadatas.append(meta)

    collection.upsert(
        ids=chunk_ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )


def semantic_search(
    query: str,
    top_k: int = TOP_K_RESULTS,
    doc_ids: Optional[List[str]] = None,
    threshold: float = SIMILARITY_THRESHOLD,
) -> List[Dict]:
    """
    Returns list of dicts:
      {chunk_id, document_id, text, distance, confidence, page_number}
    sorted by confidence descending.
    """
    collection = _get_collection()
    query_embedding = embed_one(query)

    where: Optional[Dict] = None
    if doc_ids:
        if len(doc_ids) == 1:
            where = {"document_id": doc_ids[0]}
        else:
            where = {"document_id": {"$in": doc_ids}}

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 2, max(collection.count(), 1)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    hits = []
    ids = results["ids"][0]
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    for cid, text, meta, dist in zip(ids, docs, metas, dists):
        # cosine distance ∈ [0,2]; convert to similarity [0,1]
        confidence = max(0.0, 1.0 - dist / 2.0)
        if confidence < threshold:
            continue
        hits.append(
            {
                "chunk_id": cid,
                "document_id": meta.get("document_id", ""),
                "text": text,
                "distance": dist,
                "confidence": round(confidence, 4),
                "page_number": meta.get("page_number", 1),
                "chunk_index": meta.get("chunk_index", 0),
            }
        )

    hits.sort(key=lambda x: x["confidence"], reverse=True)
    return hits[:top_k]


def delete_document_vectors(doc_id: str) -> None:
    """Remove all chunks for a document from ChromaDB."""
    collection = _get_collection()
    try:
        results = collection.get(where={"document_id": doc_id}, include=[])
        if results["ids"]:
            collection.delete(ids=results["ids"])
    except Exception:
        pass


def get_vector_store_stats() -> Dict[str, int]:
    try:
        collection = _get_collection()
        count = collection.count()
        return {"total_vectors": count}
    except Exception:
        return {"total_vectors": 0}


def collection_count() -> int:
    return get_vector_store_stats()["total_vectors"]


def clear_all_vectors() -> None:
    """Drop and recreate the ChromaDB collection, removing all vectors."""
    try:
        client = _get_chroma_client()
        client.delete_collection("doc_chunks")
    except Exception:
        pass
    # Clear Streamlit's resource cache so the collection is recreated fresh on next use.
    st.cache_resource.clear()
