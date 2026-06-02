"""Export – download template results as JSON, Excel, Word, or CSV."""

import json
from datetime import datetime

import streamlit as st

from config import APP_ICON, APP_TITLE
from modules.database import get_template_results, list_documents
from modules.exporter import export_csv, export_excel, export_json, export_word
from modules.template_manager import generate_template_output, get_all_templates

st.set_page_config(
    page_title=f"Export – {APP_TITLE}", page_icon="📤", layout="wide"
)


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


def _slug(name: str) -> str:
    import re
    return re.sub(r'[^\w-]', '_', name.lower())[:40]


def main():
    _require_auth()
    _sidebar()

    st.title("📤 Export")
    st.markdown(
        "Export template results or raw document data in multiple formats."
    )

    templates = get_all_templates()
    if not templates:
        st.info("No templates found. Create one in the Template Builder first.")
        return

    docs = list_documents(status="processed")

    # ── Template picker ────────────────────────────────────────────────────────
    st.markdown("### 1. Select Template")
    tmpl_names = [t["name"] for t in templates]
    selected_name = st.selectbox("Template", tmpl_names, key="export_tmpl")
    tmpl = next((t for t in templates if t["name"] == selected_name), None)

    # ── Source: existing result OR generate fresh ─────────────────────────────
    st.markdown("### 2. Choose Result")
    results_history = get_template_results(tmpl["id"])

    source_mode = st.radio(
        "Use:",
        ["Generate fresh output", "Use most recent result"],
        horizontal=True,
        disabled=(not results_history),
    )

    output: dict | None = None

    if source_mode == "Generate fresh output" or not results_history:
        st.markdown("#### Document Scope")
        if docs:
            doc_map = {f"{d['filename']} ({d['upload_date'][:10]})": d["id"] for d in docs}
            selected_doc_labels = st.multiselect(
                "Documents (all if empty)", list(doc_map.keys()), key="export_docs"
            )
            doc_ids = [doc_map[l] for l in selected_doc_labels] if selected_doc_labels else None
        else:
            doc_ids = None
            st.info("No processed documents. Upload some first.")
            return

        use_llm = st.toggle(
            "Use LLM synthesis (requires API key)",
            value=False,
            key="export_llm",
        )

        if st.button("⚡ Generate & Preview", type="primary", key="export_gen"):
            with st.spinner("Generating…"):
                output = generate_template_output(
                    tmpl["id"], doc_ids=doc_ids, use_llm=use_llm
                )
                st.session_state["export_output"] = output
                st.success("Output generated!")

        output = st.session_state.get("export_output")
        if output and output.get("template", {}).get("name") != selected_name:
            output = None  # stale

    else:
        # Use most recent saved result
        latest = results_history[0]
        output = {
            "template": tmpl,
            "doc_ids": latest.get("document_ids", []),
            "fields": latest.get("results", {}),
            "result_id": latest.get("id", ""),
        }
        st.success(f"Using result from {latest.get('generated_date','')[:19]}")

    if not output:
        st.info("Generate output above to enable downloads.")
        return

    # ── Preview ────────────────────────────────────────────────────────────────
    st.markdown("### 3. Preview & Download")
    with st.expander("📋 Result preview", expanded=True):
        for fname, fdata in output.get("fields", {}).items():
            conf = fdata.get("top_confidence", 0)
            answer = fdata.get("synthesized_answer", "")
            st.markdown(f"**{fname}** — {conf:.0%} confidence")
            if answer:
                st.markdown(f"> {answer[:400]}")
            else:
                hits = fdata.get("hits", [])
                if hits:
                    st.markdown(f"> *(top hit)* {hits[0].get('text','')[:300]}")
            st.divider()

    # ── Download buttons ──────────────────────────────────────────────────────
    slug = _slug(tmpl["name"])
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        json_bytes = export_json(output)
        st.download_button(
            label="⬇️ Download JSON",
            data=json_bytes,
            file_name=f"{slug}_{ts}.json",
            mime="application/json",
            use_container_width=True,
        )

    with col2:
        try:
            excel_bytes = export_excel(output)
            st.download_button(
                label="⬇️ Download Excel",
                data=excel_bytes,
                file_name=f"{slug}_{ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Excel export failed: {e}")

    with col3:
        try:
            word_bytes = export_word(output)
            st.download_button(
                label="⬇️ Download Word",
                data=word_bytes,
                file_name=f"{slug}_{ts}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Word export failed: {e}")

    with col4:
        csv_bytes = export_csv(output)
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_bytes,
            file_name=f"{slug}_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")
    st.caption("All exports contain the synthesized answers and confidence scores for each field.")


if __name__ == "__main__":
    main()
