"""Document Processor – upload, parse, chunk, index, and extract."""

from pathlib import Path

import streamlit as st

from config import APP_ICON, APP_TITLE, SUPPORTED_TYPES
from modules.database import (
    add_chunks,
    add_document,
    add_entities,
    find_document_by_hash,
    get_document,
    update_document,
)
from modules.document_processor import process_document
from modules.extractor import extract_metadata_llm, summarize_document
from modules.vector_store import index_chunks
from utils.helpers import file_hash, human_size

st.set_page_config(
    page_title=f"Document Processor – {APP_TITLE}", page_icon="📄", layout="wide"
)


def _require_auth():
    if not st.session_state.get("authenticated"):
        st.warning("Please log in from the Home page.")
        st.stop()


def _sidebar():
    with st.sidebar:
        st.markdown(f"## {APP_ICON} {APP_TITLE}")
        st.page_link("app.py",                              label="🏠 Home")
        st.page_link("pages/1_📊_Dashboard.py",             label="📊 Dashboard")
        st.page_link("pages/2_📄_Document_Processor.py",    label="📄 Document Processor")
        st.page_link("pages/3_📋_Template_Builder.py",      label="📋 Template Builder")
        st.page_link("pages/4_🔍_Search.py",                label="🔍 Search & Query")
        st.page_link("pages/5_📤_Export.py",                label="📤 Export")
        st.divider()
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()


def _process_one_file(uploaded_file, use_llm: bool, progress_slot, status_slot) -> None:
    """End-to-end pipeline for a single uploaded file."""
    fname = uploaded_file.name
    file_bytes = uploaded_file.read()
    fhash = file_hash(file_bytes)
    fsize = len(file_bytes)
    ftype = Path(fname).suffix.lstrip(".").lower()

    status_slot.info(f"Processing **{fname}**…")

    # ── Duplicate detection ───────────────────────────────────────────────────
    existing = find_document_by_hash(fhash)
    if existing:
        status_slot.warning(
            f"⚠️ **{fname}** is a duplicate of **{existing['filename']}** "
            f"(uploaded {existing['upload_date'][:10]}). Skipped."
        )
        return

    # ── Register in DB ────────────────────────────────────────────────────────
    doc_id = add_document(fname, ftype, fsize, fhash)
    progress_slot.progress(0.10, text="Extracting text…")

    try:
        # ── Extract text & chunk ─────────────────────────────────────────────
        result = process_document(file_bytes, fname, doc_id)
        progress_slot.progress(0.40, text="Chunking…")

        chunks = result["chunks"]
        if not chunks:
            update_document(doc_id, status="error")
            status_slot.error(f"No text extracted from {fname}.")
            return

        # ── Store chunks in SQLite ───────────────────────────────────────────
        chunk_ids = add_chunks(doc_id, chunks)
        progress_slot.progress(0.55, text="Embedding chunks…")

        # ── Embed & index in ChromaDB ────────────────────────────────────────
        texts = [c["text"] for c in chunks]
        extra_meta = [
            {"page_number": c.get("page_number", 1), "word_count": c.get("word_count", 0)}
            for c in chunks
        ]
        index_chunks(chunk_ids, texts, doc_id, extra_meta=extra_meta)
        progress_slot.progress(0.70, text="Extracting entities…")

        # ── Entities ─────────────────────────────────────────────────────────
        entities = result.get("entities", [])
        if entities:
            add_entities(doc_id, entities)

        progress_slot.progress(0.85, text="Generating metadata…")

        # ── Metadata & summary ───────────────────────────────────────────────
        meta = result["metadata"]

        if use_llm:
            llm_meta = extract_metadata_llm(result["text"][:4000], fname)
            meta.update({k: v for k, v in llm_meta.items() if v})
            summary = summarize_document(result["text"][:4000])
        else:
            summary = result["text"][:300].strip() + "…"

        update_document(
            doc_id,
            title=meta.get("title", fname),
            doc_type=meta.get("doc_type", "General"),
            status="processed",
            summary=summary,
            metadata=str(meta),
            page_count=meta.get("page_count", 1),
            processed_date=__import__("utils.helpers", fromlist=["now_iso"]).now_iso(),
        )

        progress_slot.progress(1.0, text="Done!")
        status_slot.success(
            f"✅ **{fname}** processed — "
            f"{len(chunks)} chunks, {len(entities)} entities, {meta.get('page_count',1)} page(s)."
        )

    except Exception as exc:
        update_document(doc_id, status="error")
        status_slot.error(f"❌ Failed to process {fname}: {exc}")
        import traceback
        with st.expander("Error details"):
            st.code(traceback.format_exc())


def main():
    _require_auth()
    _sidebar()

    st.title("📄 Document Processor")
    st.markdown(
        "Upload documents to extract text, generate embeddings, "
        "detect entities, and make them searchable."
    )

    # ── Settings ─────────────────────────────────────────────────────────────
    with st.expander("⚙️ Processing Options", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            use_llm = st.toggle(
                "Use LLM for metadata/summary",
                value=False,
                help="Requires OPENAI_API_KEY in .env",
            )
        with col_b:
            st.info("Chunking, embeddings, and entity extraction always run locally.")

    st.markdown("---")

    # ── Upload widget ─────────────────────────────────────────────────────────
    uploaded_files = st.file_uploader(
        "Drop files here or click Browse",
        type=SUPPORTED_TYPES,
        accept_multiple_files=True,
        label_visibility="visible",
    )

    if not uploaded_files:
        st.markdown(
            """
**Supported formats:**
`PDF` · `DOCX` · `TXT` · `PNG` · `JPG` · `JPEG` · `TIFF` · `BMP`

> 💡 OCR is applied automatically to images.
> Duplicate files (detected by SHA-256) are skipped.
"""
        )
        return

    st.markdown(f"**{len(uploaded_files)} file(s) selected**")

    if st.button("🚀 Process All Files", type="primary", use_container_width=True):
        for i, uf in enumerate(uploaded_files):
            st.markdown(f"#### [{i+1}/{len(uploaded_files)}] {uf.name}")
            progress_slot = st.progress(0, text="Starting…")
            status_slot = st.empty()
            _process_one_file(uf, use_llm, progress_slot, status_slot)
            st.markdown("---")

        st.balloons()
        st.success("All files processed! Head to the Dashboard or Template Builder.")


if __name__ == "__main__":
    main()
