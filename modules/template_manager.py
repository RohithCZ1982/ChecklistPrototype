"""Template creation, storage, and output generation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.database import (
    add_template,
    delete_template,
    get_template,
    get_template_results,
    keyword_search_chunks,
    list_templates,
    save_template_result,
    update_template,
)
from modules.extractor import synthesize_field_answer
from modules.vector_store import semantic_search
from utils.helpers import similarity_to_confidence


# ─── CRUD wrappers ────────────────────────────────────────────────────────────

def create_template(name: str, description: str, fields: List[Dict]) -> str:
    """
    fields: list of {name, description, search_mode}
    search_mode: 'semantic' | 'keyword' | 'both'
    """
    return add_template(name, description, fields)


def get_all_templates() -> List[Dict]:
    return list_templates()


def load_template(template_id: str) -> Optional[Dict]:
    return get_template(template_id)


def edit_template(template_id: str, name: str, description: str, fields: List[Dict]) -> None:
    update_template(template_id, name, description, fields)


def remove_template(template_id: str) -> None:
    delete_template(template_id)


# ─── Core: Generate Template Output ──────────────────────────────────────────

def generate_template_output(
    template_id: str,
    doc_ids: Optional[List[str]] = None,
    top_k: int = 5,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    For each template field, search across indexed documents and compile results.

    Returns:
      {
        "template": {...},
        "doc_ids": [...],
        "fields": {
          "field_name": {
            "hits": [{text, document_id, confidence, page_number, source}, ...],
            "synthesized_answer": "...",
            "top_confidence": 0.87,
          },
          ...
        }
      }
    """
    template = get_template(template_id)
    if not template:
        raise ValueError(f"Template {template_id!r} not found.")

    output: Dict[str, Any] = {
        "template": template,
        "doc_ids": doc_ids or [],
        "fields": {},
    }

    for field in template["fields"]:
        field_name = field.get("name", "")
        field_desc = field.get("description", "")
        search_mode = field.get("search_mode", "both")
        query = field_desc if field_desc else field_name

        hits = _search_for_field(
            query=query,
            doc_ids=doc_ids,
            top_k=top_k,
            mode=search_mode,
        )

        synthesized = ""
        if use_llm and hits:
            synthesized = synthesize_field_answer(
                field_name=field_name,
                field_description=field_desc,
                context_chunks=[h["text"] for h in hits],
            )

        top_conf = hits[0]["confidence"] if hits else 0.0

        output["fields"][field_name] = {
            "hits": hits,
            "synthesized_answer": synthesized,
            "top_confidence": top_conf,
            "field_description": field_desc,
            "search_mode": search_mode,
        }

    # Persist the result
    result_id = save_template_result(template_id, doc_ids or [], output["fields"])
    output["result_id"] = result_id

    return output


def _search_for_field(
    query: str,
    doc_ids: Optional[List[str]],
    top_k: int,
    mode: str,
) -> List[Dict]:
    """Merge semantic + keyword hits, deduplicate by chunk_id."""
    hits_map: Dict[str, Dict] = {}

    if mode in ("semantic", "both"):
        for hit in semantic_search(query, top_k=top_k, doc_ids=doc_ids, threshold=0.15):
            hits_map[hit["chunk_id"]] = hit

    if mode in ("keyword", "both"):
        kw_rows = keyword_search_chunks(query, doc_ids=doc_ids, limit=top_k)
        for row in kw_rows:
            cid = row["id"]
            if cid not in hits_map:
                hits_map[cid] = {
                    "chunk_id": cid,
                    "document_id": row["document_id"],
                    "text": row["text"],
                    "confidence": 0.55,  # keyword match gets a fixed baseline
                    "page_number": row.get("page_number", 1),
                    "source": "keyword",
                }

    results = list(hits_map.values())
    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:top_k]


# ─── Result history ───────────────────────────────────────────────────────────

def get_results_history(template_id: str) -> List[Dict]:
    return get_template_results(template_id)
