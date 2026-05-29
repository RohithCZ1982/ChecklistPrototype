"""Intelligent text chunking utilities."""

import re
from typing import List, Dict, Tuple

from config import CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK_SIZE


# ─── Sentence splitting ───────────────────────────────────────────────────────

_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def split_sentences(text: str) -> List[str]:
    """Split text into sentences using a simple regex heuristic."""
    # Handle common abbreviations
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|Fig|No)\.\s', r'\1<DOT> ', text)
    parts = _SENT_RE.split(text)
    parts = [p.replace('<DOT> ', '. ').strip() for p in parts if p.strip()]
    return parts


def split_paragraphs(text: str) -> List[str]:
    """Split text by paragraph (double newline)."""
    blocks = re.split(r'\n{2,}', text)
    return [b.strip() for b in blocks if b.strip()]


# ─── Word count helper ────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(text.split())


# ─── Core chunker ─────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    min_size: int = MIN_CHUNK_SIZE,
    page_number: int = 1,
) -> List[Dict]:
    """
    Split text into overlapping word-count-based chunks, respecting sentence
    boundaries where possible.

    Returns list of dicts: {text, page_number, char_start, char_end, word_count}.
    """
    if not text or not text.strip():
        return []

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: List[Dict] = []
    current_words: List[str] = []
    current_sents: List[str] = []
    char_cursor = 0

    def flush(words: List[str], sents: List[str]) -> Dict:
        chunk_text_str = " ".join(sents)
        c_start = text.find(sents[0]) if sents else 0
        return {
            "text": chunk_text_str,
            "page_number": page_number,
            "char_start": c_start,
            "char_end": c_start + len(chunk_text_str),
            "word_count": len(words),
        }

    for sent in sentences:
        sent_words = sent.split()
        if not sent_words:
            continue

        # If adding this sentence exceeds chunk_size, flush current buffer
        if current_words and (len(current_words) + len(sent_words)) > chunk_size:
            if len(current_words) >= min_size:
                chunks.append(flush(current_words, current_sents))

            # Overlap: keep tail sentences that fit within `overlap` words
            overlap_sents: List[str] = []
            overlap_words: List[str] = []
            for s in reversed(current_sents):
                ws = s.split()
                if len(overlap_words) + len(ws) <= overlap:
                    overlap_sents.insert(0, s)
                    overlap_words = ws + overlap_words
                else:
                    break
            current_sents = overlap_sents
            current_words = overlap_words

        current_sents.append(sent)
        current_words.extend(sent_words)

    # Flush remainder
    if current_words and len(current_words) >= min_size:
        chunks.append(flush(current_words, current_sents))
    elif current_words and chunks:
        # Merge tiny tail into last chunk
        last = chunks[-1]
        merged = last["text"] + " " + " ".join(current_sents)
        chunks[-1] = {**last, "text": merged, "word_count": last["word_count"] + len(current_words)}
    elif current_words:
        chunks.append(flush(current_words, current_sents))

    return chunks


def chunk_by_page(pages: List[Tuple[int, str]], **kwargs) -> List[Dict]:
    """
    Chunk a list of (page_number, page_text) tuples, preserving page provenance.
    """
    all_chunks: List[Dict] = []
    for page_num, page_text in pages:
        page_chunks = chunk_text(page_text, page_number=page_num, **kwargs)
        all_chunks.extend(page_chunks)
    return all_chunks
