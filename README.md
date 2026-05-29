# 🧠 AI Document Intelligence

A production-ready platform for intelligent document analysis, semantic search,
and automated information extraction via a template system.

---

## Project Structure

```
ChecklistPrototype/
├── app.py                          # Main entry point + login
├── config.py                       # All configuration (env-driven)
├── requirements.txt
├── .env.example
│
├── modules/
│   ├── database.py                 # SQLite metadata store
│   ├── document_processor.py       # PDF/DOCX/TXT/image extraction
│   ├── vector_store.py             # ChromaDB + sentence-transformers
│   ├── template_manager.py         # Template CRUD + output generation
│   ├── search_engine.py            # Semantic + keyword search, RAG Q&A
│   ├── extractor.py                # Optional LLM (OpenAI) extraction
│   └── exporter.py                 # JSON / Excel / Word / CSV export
│
├── utils/
│   ├── chunker.py                  # Intelligent sentence-aware chunking
│   └── helpers.py                  # NER regex, hashing, formatting
│
├── pages/
│   ├── 1_📊_Dashboard.py           # Document library + entity viewer
│   ├── 2_📄_Document_Processor.py  # Upload + process pipeline
│   ├── 3_📋_Template_Builder.py    # Create/run templates
│   ├── 4_🔍_Search.py              # Global search + Q&A + similarity
│   └── 5_📤_Export.py              # Download results
│
└── data/                           # Runtime data (git-ignored)
    ├── uploads/                    # Stored document files
    ├── chroma_db/                  # ChromaDB persistent vectors
    └── metadata.db                 # SQLite database
```

---

## Setup

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd ChecklistPrototype
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

**Optional – spaCy NER model** (improves entity extraction):
```bash
python -m spacy download en_core_web_sm
```

**Optional – Tesseract OCR** (for image files):
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows: download installer from https://github.com/UB-Mannheim/tesseract/wiki
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env – add OPENAI_API_KEY if you want LLM features
```

### 4. Run

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

Default credentials: `admin` / `admin123`

---

## Feature Overview

| Feature | Description |
|---|---|
| Document Upload | PDF, DOCX, TXT, PNG/JPG/TIFF (OCR) |
| Duplicate Detection | SHA-256 hash check on upload |
| Semantic Chunking | Sentence-aware overlapping chunks |
| Vector Embeddings | `all-MiniLM-L6-v2` via sentence-transformers |
| Vector Store | ChromaDB (persistent, cosine similarity) |
| Keyword Search | SQLite FTS5 full-text search |
| Combined Search | Semantic + keyword merged results |
| Named Entity Recognition | Regex NER + optional spaCy |
| Template Builder | Define fields → auto-extract from docs |
| LLM Synthesis | GPT-4o-mini answer synthesis (optional) |
| RAG Q&A | Ask natural-language questions |
| Document Similarity | Pairwise Jaccard similarity matrix |
| Export | JSON, Excel (multi-sheet), Word, CSV |
| Authentication | Simple username/password session auth |
| Dark Mode | Toggle in sidebar |

---

## Tech Stack

| Component | Library |
|---|---|
| UI | Streamlit 1.35+ |
| PDF parsing | PyMuPDF (fitz) |
| Word parsing | python-docx |
| OCR | pytesseract + Pillow |
| Embeddings | sentence-transformers |
| Vector store | ChromaDB (persistent) |
| Metadata DB | SQLite (stdlib) |
| LLM | OpenAI API (gpt-4o-mini) |
| NER | regex + spaCy (optional) |
| Excel export | openpyxl |
| Word export | python-docx |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AUTH_USERNAME` | `admin` | Login username |
| `AUTH_PASSWORD` | `admin123` | Login password |
| `OPENAI_API_KEY` | *(empty)* | Required for LLM features |
| `OPENAI_BASE_URL` | OpenAI | Override for Grok/Azure/etc. |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformer model |
| `CHUNK_SIZE` | `500` | Target words per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap words between chunks |
| `TOP_K_RESULTS` | `5` | Default search result count |
| `SIMILARITY_THRESHOLD` | `0.25` | Minimum confidence to include |

---

## Using an Alternative LLM (e.g. Grok / Azure)

Set in `.env`:
```
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.x.ai/v1   # Grok example
LLM_MODEL=grok-3-mini
```

The app uses the OpenAI-compatible SDK, so any endpoint works.

---

## Offline Mode

All core features (upload, chunking, embedding, search, templates) work
**without** an API key. LLM features (metadata extraction, answer synthesis)
are silently skipped and replaced with extracted snippets.
