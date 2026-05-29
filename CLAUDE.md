# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**AI Document Intelligence** — a Streamlit multi-page app for document ingestion,
semantic search, and automated information extraction via a template system.

## Commands

```bash
# Install
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # optional, better NER

# Run
streamlit run app.py                       # serves on http://localhost:8501

# Syntax-check all modules (no test suite yet)
python -c "import py_compile, pathlib; [py_compile.compile(str(f), doraise=True) for f in pathlib.Path('.').rglob('*.py') if '.git' not in str(f)]"
```

There is **no test suite, linter config, or CI** yet. Validate changes by
compiling (above) and running the app manually.

## Architecture

Three layers, strictly separated:

1. **`pages/`** — Streamlit UI only. Each page is self-contained with its own
   `_require_auth()`, `_sidebar()`, and `main()`. Pages import from `modules/`
   and `utils/` but never talk to ChromaDB/SQLite directly.
2. **`modules/`** — business logic. One responsibility each:
   - `database.py` — the **only** place that touches SQLite. All other code
     calls its functions. Schema lives in `init_db()`.
   - `vector_store.py` — the **only** place that touches ChromaDB and the
     embedding model. Both are wrapped in `@st.cache_resource`.
   - `document_processor.py` — file → text → chunks → entities.
   - `template_manager.py` — template CRUD + `generate_template_output()` (the
     core feature: searches docs for each template field).
   - `search_engine.py` — merges semantic + keyword hits; RAG Q&A; similarity.
   - `extractor.py` — all OpenAI/LLM calls. Gracefully degrades when no API key.
   - `exporter.py` — JSON/Excel/Word/CSV serialization.
3. **`utils/`** — pure, dependency-light helpers (`chunker.py`, `helpers.py`).
   No Streamlit, no DB.

`config.py` reads everything from `.env` via `python-dotenv` and creates the
`data/` directories at import time.

## Data flow (upload → searchable)

`pages/2` → `document_processor.process_document()` (extract + chunk + NER)
→ `database.add_chunks()` (SQLite + FTS5) → `vector_store.index_chunks()`
(embed + ChromaDB) → `database.update_document(status='processed')`.

## Conventions

- **Search dual-write**: every chunk goes into both SQLite FTS5 (keyword) and
  ChromaDB (semantic). Keep them in sync — if you add a chunk path, write both.
- **Confidence**: cosine distance → confidence via `1 - distance/2` (range
  [0,1]). Keyword-only hits get a fixed baseline (~0.5–0.55). Use
  `helpers.confidence_color()` for UI badges.
- **Offline-first**: LLM features must degrade gracefully. Check
  `extractor._llm_available()` and provide a non-LLM fallback (snippet/extract).
- **ChromaDB metadata** only accepts str/int/float/bool — filter dicts before
  upserting (see `vector_store.index_chunks`).
- **Caching**: embedding model and Chroma client use `@st.cache_resource`.
  Never instantiate them per-request.
- **Auth gate**: every page calls `_require_auth()` first; it `st.stop()`s if
  the session isn't authenticated.
- **Type hints** on all new functions; module-level docstrings; section
  comment banners (`# ─── Name ───`) matching the existing style.
- **IDs** are `uuid4` strings generated in `database.py`.
- **Dedup** is by SHA-256 (`helpers.file_hash`) — checked before insert.

## Persistence

All runtime state lives in `data/` (gitignored): `metadata.db` (SQLite),
`chroma_db/` (vectors), `uploads/` (original files). Deleting a document must
clean all three — see `pages/1` `_delete_document()`.

## Gotchas

- Page filenames contain emoji and use Streamlit's numeric-prefix ordering
  convention (`1_📊_Dashboard.py`). `st.page_link` targets must match exactly.
- DOCX and TXT have no real pages; they're split into ~30-paragraph / ~3000-char
  "virtual pages" for provenance.
- `requirements.txt` pins `hashlib2` which is unused (stdlib `hashlib` is used);
  harmless but can be removed.
