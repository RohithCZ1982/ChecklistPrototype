"""General utility helpers."""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def file_hash(file_bytes: bytes) -> str:
    """SHA-256 hash of raw bytes."""
    return hashlib.sha256(file_bytes).hexdigest()


def slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


def human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def truncate(text: str, max_chars: int = 200) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def clean_text(text: str) -> str:
    """Remove excess whitespace and non-printable characters."""
    text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E -￿]', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_dates(text: str) -> List[str]:
    """Regex-based date extraction."""
    patterns = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, text, re.IGNORECASE))
    return list(dict.fromkeys(found))  # deduplicate, preserve order


def extract_amounts(text: str) -> List[str]:
    """Regex-based monetary amount extraction."""
    pattern = r'\$[\d,]+(?:\.\d{1,2})?|\b\d[\d,]*(?:\.\d{1,2})?\s*(?:USD|EUR|GBP|INR|dollars?|euros?|pounds?)\b'
    return re.findall(pattern, text, re.IGNORECASE)


def extract_emails(text: str) -> List[str]:
    return re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', text)


def extract_phone_numbers(text: str) -> List[str]:
    return re.findall(
        r'\b(?:\+?\d[\d\s\-().]{7,}\d)\b', text
    )


def extract_urls(text: str) -> List[str]:
    return re.findall(r'https?://[^\s<>"\']+', text)


def regex_ner(text: str) -> List[Dict]:
    """
    Lightweight regex-based Named Entity Recognition.
    Returns list of {type, text, confidence}.
    """
    entities = []

    for d in extract_dates(text):
        entities.append({"type": "DATE", "text": d, "confidence": 0.85})
    for a in extract_amounts(text):
        entities.append({"type": "MONEY", "text": a, "confidence": 0.85})
    for e in extract_emails(text):
        entities.append({"type": "EMAIL", "text": e, "confidence": 0.95})
    for u in extract_urls(text):
        entities.append({"type": "URL", "text": u, "confidence": 0.95})

    # Capitalized multi-word phrases (rough PERSON/ORG detection)
    caps = re.findall(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b', text)
    seen = set()
    for c in caps:
        if c not in seen:
            seen.add(c)
            entities.append({"type": "PROPER_NOUN", "text": c, "confidence": 0.6})

    return entities


def is_markdown_table(text: str) -> bool:
    """Return True if text contains a well-formed markdown table (≥2 data rows)."""
    lines = [l for l in text.strip().split("\n") if l.strip()]
    pipe_lines = [l for l in lines if "|" in l]
    if len(pipe_lines) < 2:
        return False
    data_rows = [l for l in pipe_lines if not re.match(r"^\s*\|[-:\s|]+\|\s*$", l)]
    return len(data_rows) >= 2


def confidence_color(score: float) -> str:
    """Return a color string based on confidence score."""
    if score >= 0.75:
        return "green"
    if score >= 0.5:
        return "orange"
    return "red"


def similarity_to_confidence(distance: float) -> float:
    """
    Convert a cosine distance (0=identical, 2=opposite) to a [0,1] confidence.
    ChromaDB returns L2 or cosine distances; here we assume cosine distance ∈ [0,2].
    """
    return max(0.0, min(1.0, 1.0 - distance / 2.0))


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def safe_json_loads(s: Any, default: Any = None) -> Any:
    import json
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s or "")
    except Exception:
        return default if default is not None else {}
