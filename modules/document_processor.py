"""Document ingestion, text extraction, and entity detection."""

import io
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import UPLOAD_DIR
from utils.chunker import chunk_by_page, chunk_text
from utils.helpers import clean_text, file_hash, regex_ner


# ─── Text extraction ──────────────────────────────────────────────────────────

def extract_pdf(file_path: Path) -> Tuple[str, List[Tuple[int, str]], int]:
    """
    Returns (full_text, [(page_num, page_text), ...], page_count).
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))
        pages = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                pages.append((i, clean_text(text)))
        full_text = "\n\n".join(t for _, t in pages)
        return full_text, pages, len(doc)
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Run: pip install PyMuPDF")
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}")


def extract_docx(file_path: Path) -> Tuple[str, List[Tuple[int, str]], int]:
    """Extract text from DOCX. Pages are approximated by paragraph groups."""
    try:
        from docx import Document
        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        # Group ~30 paragraphs per virtual page
        page_size = 30
        pages = []
        for i in range(0, max(len(paragraphs), 1), page_size):
            group = paragraphs[i : i + page_size]
            page_text = "\n".join(group)
            pages.append((i // page_size + 1, clean_text(page_text)))

        # Also extract tables
        table_texts = []
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text for cell in row.cells if cell.text.strip())
                if row_text:
                    table_texts.append(row_text)

        if table_texts:
            pages.append((len(pages) + 1, "TABLES:\n" + "\n".join(table_texts)))

        full_text = clean_text("\n\n".join(t for _, t in pages))
        return full_text, pages, len(pages)
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")
    except Exception as e:
        raise RuntimeError(f"DOCX extraction failed: {e}")


def extract_image(file_path: Path) -> Tuple[str, List[Tuple[int, str]], int]:
    """OCR image using pytesseract."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(str(file_path))
        text = pytesseract.image_to_string(img)
        text = clean_text(text)
        return text, [(1, text)], 1
    except ImportError:
        raise RuntimeError("pytesseract or Pillow not installed.")
    except Exception as e:
        raise RuntimeError(f"Image OCR failed: {e}")


def extract_txt(file_path: Path) -> Tuple[str, List[Tuple[int, str]], int]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            text = file_path.read_text(encoding=enc)
            text = clean_text(text)
            # Split into virtual pages of ~3000 chars
            pages = []
            chunk_sz = 3000
            for i in range(0, max(len(text), 1), chunk_sz):
                pages.append((i // chunk_sz + 1, text[i : i + chunk_sz]))
            return text, pages, len(pages)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Could not decode text file.")


def extract_text(file_path: Path, file_type: str) -> Tuple[str, List[Tuple[int, str]], int]:
    """Dispatch extraction based on file type."""
    ft = file_type.lower().lstrip(".")
    if ft == "pdf":
        return extract_pdf(file_path)
    if ft == "docx":
        return extract_docx(file_path)
    if ft in ("png", "jpg", "jpeg", "tiff", "bmp", "gif"):
        return extract_image(file_path)
    if ft == "txt":
        return extract_txt(file_path)
    raise ValueError(f"Unsupported file type: {ft}")


# ─── Metadata inference ───────────────────────────────────────────────────────

_DOC_TYPE_PATTERNS = {
    "Invoice": re.compile(r'\binvoice\b', re.I),
    "Contract": re.compile(r'\b(contract|agreement|terms)\b', re.I),
    "Report": re.compile(r'\b(report|analysis|summary|review)\b', re.I),
    "Resume": re.compile(r'\b(resume|curriculum vitae|cv|work experience)\b', re.I),
    "Legal": re.compile(r'\b(plaintiff|defendant|court|law|clause|attorney)\b', re.I),
    "Financial": re.compile(r'\b(balance sheet|profit|loss|revenue|financial statement)\b', re.I),
    "Medical": re.compile(r'\b(patient|diagnosis|prescription|medical|clinical)\b', re.I),
    "Research": re.compile(r'\b(abstract|methodology|hypothesis|findings|literature)\b', re.I),
}


def infer_doc_type(text: str) -> str:
    for label, pattern in _DOC_TYPE_PATTERNS.items():
        if pattern.search(text[:3000]):
            return label
    return "General"


def infer_title(text: str, filename: str) -> str:
    """Use first non-empty line or filename stem as title."""
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 5 and len(line) < 200:
            return line
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


# ─── Main processor ───────────────────────────────────────────────────────────

def process_document(
    file_bytes: bytes,
    filename: str,
    doc_id: str,
) -> Dict:
    """
    Full pipeline: save → extract → chunk → entities.

    Returns a dict with keys:
      text, pages, chunks, entities, metadata
    """
    file_type = Path(filename).suffix.lstrip(".").lower()
    save_path = UPLOAD_DIR / f"{doc_id}_{filename}"

    # Persist the file
    save_path.write_bytes(file_bytes)

    # Extract text
    full_text, pages, page_count = extract_text(save_path, file_type)

    # Build chunks (preserve page provenance)
    chunks = chunk_by_page(pages)

    # Lightweight NER on first 8 000 chars
    entities = regex_ner(full_text[:8000])

    # Attempt spaCy NER if available
    spacy_entities = _spacy_ner(full_text[:8000])
    entities.extend(spacy_entities)

    # Deduplicate entities by (type, text)
    seen = set()
    deduped_entities = []
    for e in entities:
        key = (e["type"], e["text"].lower())
        if key not in seen:
            seen.add(key)
            deduped_entities.append(e)

    metadata = {
        "title": infer_title(full_text, filename),
        "doc_type": infer_doc_type(full_text),
        "page_count": page_count,
        "char_count": len(full_text),
        "word_count": len(full_text.split()),
        "chunk_count": len(chunks),
    }

    return {
        "text": full_text,
        "pages": pages,
        "chunks": chunks,
        "entities": deduped_entities,
        "metadata": metadata,
        "save_path": str(save_path),
    }


def _spacy_ner(text: str) -> List[Dict]:
    """Optional spaCy NER – silently skipped if spaCy/model not available."""
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            return []
        doc = nlp(text[:5000])
        results = []
        seen = set()
        for ent in doc.ents:
            key = (ent.label_, ent.text.lower())
            if key not in seen:
                seen.add(key)
                results.append({"type": ent.label_, "text": ent.text, "confidence": 0.80})
        return results
    except ImportError:
        return []


def get_document_file_path(doc_id: str, filename: str) -> Optional[Path]:
    """Reconstruct the saved file path for a document."""
    path = UPLOAD_DIR / f"{doc_id}_{filename}"
    return path if path.exists() else None


def detect_similarity(text1: str, text2: str) -> float:
    """
    Quick Jaccard similarity between two texts based on word sets.
    Returns value in [0, 1].
    """
    words1 = set(re.findall(r'\b\w{3,}\b', text1.lower()))
    words2 = set(re.findall(r'\b\w{3,}\b', text2.lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)
