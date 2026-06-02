"""
Inspection – conduct an inspection against a saved checklist.
"""

import datetime
import re

import pandas as pd
import streamlit as st

from config import APP_ICON, APP_TITLE
from modules.checklist_manager import get_all_checklists
from modules.inspection_manager import save_inspection
from modules.template_manager import get_all_templates
from utils.helpers import is_markdown_table

st.set_page_config(
    page_title=f"Inspection – {APP_TITLE}", page_icon="📝", layout="wide"
)

_RESULT_OPTIONS = ["—", "Pass", "Fail"]


def _render_md_table(text: str) -> None:
    """Parse a markdown table string and display it as a Streamlit dataframe."""
    lines = [l for l in text.strip().split("\n") if l.strip()]
    pipe_lines = [l for l in lines if "|" in l]
    data_rows = []
    for line in pipe_lines:
        if re.match(r"^\s*\|[-:\s|]+\|\s*$", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells:
            data_rows.append(cells)
    if len(data_rows) < 2:
        st.text(text)
        return
    max_cols = max(len(r) for r in data_rows)
    data_rows = [r + [""] * (max_cols - len(r)) for r in data_rows]
    df = pd.DataFrame(data_rows[1:], columns=data_rows[0])
    st.dataframe(df, use_container_width=True, hide_index=True)


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
        st.page_link("app.py",                                  label="🏠 Home")
        st.page_link("pages/1_📊_Dashboard.py",                 label="📊 Dashboard")
        st.page_link("pages/2_📄_Document_Processor.py",        label="📄 Document Processor")
        st.page_link("pages/3_📋_Template_Builder.py",          label="📋 Template Builder")
        st.page_link("pages/4_🔍_Search.py",                    label="🔍 Search & Query")
        st.page_link("pages/5_📤_Export.py",                    label="📤 Export")
        st.page_link("pages/6_✅_Create_Checklist.py",          label="✅ Create Checklist")
        st.page_link("pages/7_📝_Inspection.py",                label="📝 Inspection")
        st.page_link("pages/8_📜_Conducted_Inspections.py",     label="📜 Conducted Inspections")
        st.divider()
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _require_auth()
    _sidebar()

    st.title("📝 Inspection")
    st.markdown("Select a checklist, fill in the details, and mark each field as Pass or Fail.")

    checklists = get_all_checklists()
    if not checklists:
        st.info("No checklists found.")
        st.page_link("pages/6_✅_Create_Checklist.py", label="➕ Create a checklist first")
        return

    # ── Header inputs ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 3, 2])
    with col1:
        cl_names = [c["name"] for c in checklists]
        selected_cl_name = st.selectbox("Checklist *", cl_names, key="insp_cl_select")
    with col2:
        insp_name = st.text_input("Inspection Name *", placeholder="e.g. Site Visit #1", key="insp_name")
    with col3:
        insp_date = st.date_input("Date of Inspection", value=datetime.date.today(), key="insp_date")

    cl = next((c for c in checklists if c["name"] == selected_cl_name), None)
    if not cl:
        return

    st.markdown("---")

    # ── Resolve templates ─────────────────────────────────────────────────────
    all_templates = {t["id"]: t for t in get_all_templates()}
    ordered = [all_templates[tid] for tid in cl["template_ids"] if tid in all_templates]

    if not ordered:
        st.warning("No templates found for this checklist.")
        return

    # ── Field rows per template ────────────────────────────────────────────────
    for tmpl in ordered:
        fields = tmpl.get("fields", [])
        st.markdown(f"### {tmpl['name']}")
        if tmpl.get("description"):
            st.caption(tmpl["description"])

        if not fields:
            st.caption("No fields defined for this template.")
            st.divider()
            continue

        h1, h2, h3 = st.columns([3, 6, 2])
        h1.markdown("**Field**")
        h2.markdown("**Reference / Hint**")
        h3.markdown("**Result**")

        for i, field in enumerate(fields):
            desc = field.get("description", "") or ""
            c1, c2, c3 = st.columns([3, 6, 2])
            c1.markdown(f"**{field.get('name', '—')}**")
            if is_markdown_table(desc):
                c2.caption("📊 Reference table — see below")
            else:
                c2.caption(desc[:120] + "…" if len(desc) > 120 else desc or "—")
            c3.selectbox(
                "",
                _RESULT_OPTIONS,
                key=f"insp_{tmpl['id']}_{i}",
                label_visibility="collapsed",
            )
            # Render table below the row if description is a table
            if is_markdown_table(desc):
                with st.expander("📊 Reference Table", expanded=True):
                    _render_md_table(desc)

        st.divider()

    # ── Save ──────────────────────────────────────────────────────────────────
    if st.button("💾 Save Inspection", type="primary", key="insp_save"):
        if not insp_name.strip():
            st.error("Inspection name is required.")
            return

        results: dict = {}
        for tmpl in ordered:
            results[tmpl["id"]] = {}
            for i, field in enumerate(tmpl.get("fields", [])):
                results[tmpl["id"]][field["name"]] = st.session_state.get(
                    f"insp_{tmpl['id']}_{i}", "—"
                )

        try:
            save_inspection(
                name=insp_name.strip(),
                checklist_id=cl["id"],
                checklist_name=cl["name"],
                inspection_date=str(insp_date),
                results=results,
            )
            st.success(f"Inspection **{insp_name}** saved!")
            st.page_link(
                "pages/8_📜_Conducted_Inspections.py",
                label="📜 View in Conducted Inspections",
            )
        except Exception as e:
            st.error(f"Failed to save inspection: {e}")


if __name__ == "__main__":
    main()
