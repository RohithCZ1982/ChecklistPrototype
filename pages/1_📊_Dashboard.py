"""Dashboard – document library, processing status, and statistics."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config import APP_ICON, APP_TITLE, UPLOAD_DIR
from modules.database import clear_all_data, delete_document, get_document, get_entities, get_stats, list_documents
from modules.vector_store import clear_all_vectors, delete_document_vectors, get_vector_store_stats
from utils.helpers import human_size, safe_json_loads, truncate

st.set_page_config(page_title=f"Dashboard – {APP_TITLE}", page_icon="📊", layout="wide")


def _require_auth():
    if not st.session_state.get("authenticated"):
        st.warning("Please log in from the Home page.")
        st.stop()


def _sidebar():
    with st.sidebar:
        st.markdown(
            "<style>[data-testid=\"stSidebarNav\"]{display:none!important}</style>",
            unsafe_allow_html=True,
        )
        st.markdown(f"## {APP_ICON} {APP_TITLE}")
        st.page_link("app.py",                              label="🏠 Home")
        st.page_link("pages/1_📊_Dashboard.py",             label="📊 Dashboard")
        st.page_link("pages/2_📄_Document_Processor.py",    label="📄 Document Processor")
        st.page_link("pages/3_📋_Template_Builder.py",      label="📋 Template Builder")
        st.page_link("pages/4_🔍_Search.py",                label="🔍 Search & Query")
        st.page_link("pages/5_📤_Export.py",                label="📤 Export")
        st.page_link("pages/6_✅_Create_Checklist.py",          label="✅ Create Checklist")
        st.page_link("pages/7_📝_Inspection.py",                label="📝 Inspection")
        st.page_link("pages/8_📜_Conducted_Inspections.py",     label="📜 Conducted Inspections")
        st.divider()
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()


def _status_badge(status: str) -> str:
    color = {"processed": "🟢", "pending": "🟡", "error": "🔴"}.get(status, "⚪")
    return f"{color} {status.capitalize()}"


def _delete_document(doc_id: str, filename: str):
    try:
        delete_document_vectors(doc_id)
        delete_document(doc_id)
        # Remove file from disk
        for f in UPLOAD_DIR.glob(f"{doc_id}_*"):
            f.unlink(missing_ok=True)
        st.success(f"Deleted: {filename}")
        st.rerun()
    except Exception as e:
        st.error(f"Delete failed: {e}")


def main():
    _require_auth()
    _sidebar()

    st.title("📊 Document Dashboard")

    # ── Stats row ────────────────────────────────────────────────────────────
    stats = get_stats()
    vs_stats = get_vector_store_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Documents",  stats["documents"])
    c2.metric("Processed",        stats["processed"])
    c3.metric("Chunks Indexed",   stats["chunks"])
    c4.metric("Vectors in Store", vs_stats["total_vectors"])
    c5.metric("Entities Found",   stats["entities"])

    st.markdown("---")

    # ── Filters ──────────────────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        search_q = st.text_input("🔎 Filter documents", placeholder="Search by filename or title…")
    with col_f2:
        status_filter = st.selectbox("Status", ["All", "processed", "pending", "error"])
    with col_f3:
        type_filter = st.selectbox("Type", ["All", "pdf", "docx", "txt", "png", "jpg"])

    docs = list_documents()

    # Apply filters
    if search_q:
        docs = [d for d in docs if search_q.lower() in d["filename"].lower()
                or search_q.lower() in (d.get("title") or "").lower()]
    if status_filter != "All":
        docs = [d for d in docs if d["status"] == status_filter]
    if type_filter != "All":
        docs = [d for d in docs if d["file_type"].lower() == type_filter]

    if not docs:
        st.info("No documents found. Upload some in the Document Processor.")
        return

    st.markdown(f"**{len(docs)} document(s) found**")

    # ── Document table ────────────────────────────────────────────────────────
    for doc in docs:
        meta = safe_json_loads(doc.get("metadata"), {})
        with st.expander(
            f"{_status_badge(doc['status'])}  **{doc['filename']}**  "
            f"— {human_size(doc.get('file_size') or 0)}  |  "
            f"{doc.get('file_type','').upper()}  |  "
            f"{doc.get('upload_date','')[:10]}",
            expanded=False,
        ):
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                st.markdown("**Metadata**")
                st.write(f"- **Title:** {doc.get('title') or meta.get('title', '—')}")
                st.write(f"- **Type:** {doc.get('doc_type') or meta.get('doc_type', '—')}")
                st.write(f"- **Pages:** {meta.get('page_count', '—')}")
                st.write(f"- **Chunks:** {doc.get('chunk_count', 0)}")
                st.write(f"- **Words:** {meta.get('word_count', '—')}")

            with col2:
                st.markdown("**Summary**")
                summary = doc.get("summary") or meta.get("summary", "No summary available.")
                st.write(truncate(summary, 350))

            with col3:
                st.markdown("**Actions**")
                if st.button("🔍 View Entities", key=f"ent_{doc['id']}"):
                    st.session_state[f"show_entities_{doc['id']}"] = True
                with st.popover("🗑️ Delete", use_container_width=True):
                    st.warning(
                        f"Permanently delete **{doc['filename']}**?\n\n"
                        "This removes the file, all chunks, and all vectors. "
                        "This cannot be undone."
                    )
                    if st.button(
                        "Yes, delete permanently",
                        key=f"confirm_del_{doc['id']}",
                        type="primary",
                        use_container_width=True,
                    ):
                        _delete_document(doc["id"], doc["filename"])

            # Entity viewer
            if st.session_state.get(f"show_entities_{doc['id']}"):
                entities = get_entities(doc["id"])
                if entities:
                    df = pd.DataFrame(entities)[["entity_type", "entity_text", "confidence"]]
                    df.columns = ["Type", "Entity", "Confidence"]
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("No entities extracted for this document.")
                if st.button("Hide entities", key=f"hide_ent_{doc['id']}"):
                    st.session_state[f"show_entities_{doc['id']}"] = False
                    st.rerun()

    st.markdown("---")

    # ── Type breakdown chart ──────────────────────────────────────────────────
    if docs:
        st.markdown("### Document Type Breakdown")
        all_docs = list_documents()
        type_counts: dict = {}
        for d in all_docs:
            t = d["file_type"].upper()
            type_counts[t] = type_counts.get(t, 0) + 1
        type_df = pd.DataFrame(
            list(type_counts.items()), columns=["Type", "Count"]
        ).sort_values("Count", ascending=False)
        st.bar_chart(type_df.set_index("Type"))

    # ── Danger Zone ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⚠️ Danger Zone")
    st.caption("Irreversible actions that affect all application data.")

    with st.popover("🔧 Repair Database", use_container_width=False):
        st.warning(
            "Use this if you see **'database disk image is malformed'** or other "
            "SQLite errors. This rebuilds the database file from scratch.\n\n"
            "**Documents, vectors, and uploaded files are preserved.** "
            "Only SQLite metadata (documents list, chunks, templates, checklists, "
            "inspections) is rebuilt — you will need to re-process any documents."
        )
        if st.button("Rebuild database", key="repair_db_btn", use_container_width=True):
            try:
                from modules.database import clear_all_data, init_db
                clear_all_data()   # deletes the file and calls init_db()
                st.success("Database rebuilt. Please re-process your documents.")
                st.rerun()
            except Exception as e:
                st.error(f"Repair failed: {e}")

    st.write("")  # spacer

    with st.popover("🗑️ Clear All Data", use_container_width=False):
        st.error(
            "**This will permanently delete:**\n"
            "- All documents, chunks, and vectors\n"
            "- All templates and generated results\n"
            "- All checklists and inspections\n"
            "- All uploaded files on disk\n\n"
            "This **cannot** be undone."
        )
        confirm_text = st.text_input(
            "Type **DELETE** to confirm",
            placeholder="DELETE",
            key="clear_all_confirm",
        )
        if st.button(
            "Yes, delete everything",
            type="primary",
            use_container_width=True,
            key="clear_all_btn",
            disabled=confirm_text.strip() != "DELETE",
        ):
            try:
                # 1. Clear SQLite
                clear_all_data()
                # 2. Clear ChromaDB
                clear_all_vectors()
                # 3. Delete uploaded files
                for f in UPLOAD_DIR.glob("*"):
                    f.unlink(missing_ok=True)
                # 4. Wipe data-related session state keys
                for k in list(st.session_state.keys()):
                    if k not in ("authenticated", "username", "dark_mode"):
                        st.session_state.pop(k, None)
                st.success("All data cleared.")
                st.rerun()
            except Exception as e:
                st.error(f"Clear failed: {e}")


if __name__ == "__main__":
    main()
