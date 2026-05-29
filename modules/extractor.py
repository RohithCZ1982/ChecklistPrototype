"""LLM-powered extraction and summarization (requires OpenAI API key)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from config import LLM_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL


def _llm_available() -> bool:
    return bool(OPENAI_API_KEY and OPENAI_API_KEY.strip().startswith("sk-"))


def _client():
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


def _chat(messages: List[Dict], max_tokens: int = 1024) -> str:
    try:
        client = _client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[LLM error: {e}]"


# ─── Summarization ────────────────────────────────────────────────────────────

def summarize_document(text: str) -> str:
    """Return a 2-3 sentence document summary."""
    if not _llm_available():
        # Fallback: first 400 chars
        first = " ".join(text.split()[:80])
        return first + ("…" if len(text.split()) > 80 else "")

    prompt = (
        "Summarize the following document in 2-3 sentences. "
        "Be concise and factual.\n\n"
        f"DOCUMENT:\n{text[:4000]}"
    )
    return _chat([{"role": "user", "content": prompt}], max_tokens=200)


# ─── Metadata extraction ──────────────────────────────────────────────────────

def extract_metadata_llm(text: str, filename: str) -> Dict[str, Any]:
    """
    Return a dict with keys: title, doc_type, key_dates, key_amounts, summary.
    Falls back to empty values if LLM is unavailable.
    """
    if not _llm_available():
        return {}

    prompt = f"""Extract structured metadata from this document excerpt.
Return ONLY valid JSON with these keys:
  title (string), doc_type (string), key_dates (list of strings),
  key_amounts (list of strings), summary (1-2 sentences).

FILENAME: {filename}
DOCUMENT:
{text[:3000]}

JSON:"""

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=400)

    # Strip markdown fences if present
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ─── Template field extraction ────────────────────────────────────────────────

def synthesize_field_answer(
    field_name: str,
    field_description: str,
    context_chunks: List[str],
) -> str:
    """
    Given a field name and a list of relevant text chunks, produce a concise answer.
    """
    if not _llm_available():
        # Return the most relevant snippet as-is
        return context_chunks[0][:400] if context_chunks else ""

    context = "\n---\n".join(context_chunks[:5])
    prompt = f"""You are an expert document analyst.
Extract the answer to the following field from the document excerpts below.
Be concise and direct. If the information is not found, say "Not found."

FIELD: {field_name}
DESCRIPTION: {field_description or 'Extract relevant information for this field.'}

DOCUMENT EXCERPTS:
{context[:3500]}

ANSWER:"""

    return _chat([{"role": "user", "content": prompt}], max_tokens=300)


# ─── Document Q&A ─────────────────────────────────────────────────────────────

def answer_question(
    question: str,
    context_chunks: List[str],
    document_titles: Optional[List[str]] = None,
) -> str:
    """RAG-style Q&A over retrieved chunks."""
    if not context_chunks:
        return "No relevant content found in the documents."

    if not _llm_available():
        return context_chunks[0][:500] if context_chunks else "No content available."

    context = "\n---\n".join(context_chunks[:6])
    source_hint = ""
    if document_titles:
        source_hint = f"\nSources: {', '.join(document_titles[:3])}"

    prompt = f"""Answer the question below using ONLY the provided document excerpts.
If the answer is not in the excerpts, say "I don't have enough information."
{source_hint}

QUESTION: {question}

DOCUMENT EXCERPTS:
{context[:4000]}

ANSWER:"""

    return _chat([{"role": "user", "content": prompt}], max_tokens=500)


# ─── Table / structured data extraction ──────────────────────────────────────

def extract_table_from_text(text: str) -> Optional[List[List[str]]]:
    """
    Attempt to extract a table from text using LLM.
    Returns list of rows (each row is a list of cell values).
    """
    if not _llm_available():
        return None

    prompt = f"""If the following text contains a table, extract it as JSON.
Return a JSON array of arrays (rows × columns) with a header row first.
If there is no table, return null.

TEXT:
{text[:2000]}

JSON:"""

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=600)
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return None
