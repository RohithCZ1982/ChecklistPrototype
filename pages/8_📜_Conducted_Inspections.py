"""
Conducted Inspections – view and review all saved inspection records.
"""

import streamlit as st

from config import APP_ICON, APP_TITLE
from modules.checklist_manager import get_all_checklists
from modules.inspection_manager import get_all_inspections
from modules.template_manager import get_all_templates

st.set_page_config(
    page_title=f"Conducted Inspections – {APP_TITLE}", page_icon="📜", layout="wide"
)

_BADGE = {"Pass": "🟢 Pass", "Fail": "🔴 Fail", "—": "⚪ —"}


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


def _result_summary(results: dict) -> tuple[int, int, int]:
    """Return (pass_count, fail_count, not_checked_count) across all templates."""
    p = f = n = 0
    for field_map in results.values():
        for v in field_map.values():
            if v == "Pass":
                p += 1
            elif v == "Fail":
                f += 1
            else:
                n += 1
    return p, f, n


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _require_auth()
    _sidebar()

    st.title("📜 Conducted Inspections")

    # ── Filter bar ────────────────────────────────────────────────────────────
    checklists = get_all_checklists()
    filter_options = ["All Checklists"] + [c["name"] for c in checklists]
    selected_filter = st.selectbox("Filter by Checklist", filter_options, key="ci_filter")

    checklist_id_filter = None
    if selected_filter != "All Checklists":
        cl = next((c for c in checklists if c["name"] == selected_filter), None)
        if cl:
            checklist_id_filter = cl["id"]

    inspections = get_all_inspections(checklist_id=checklist_id_filter)

    if not inspections:
        st.info("No inspections recorded yet.")
        st.page_link("pages/7_📝_Inspection.py", label="📝 Conduct an inspection")
        return

    st.markdown(f"**{len(inspections)} inspection(s) found**")
    st.markdown("---")

    tmpl_name_map = {t["id"]: t["name"] for t in get_all_templates()}

    # ── Inspection cards ──────────────────────────────────────────────────────
    for insp in inspections:
        p, f, n = _result_summary(insp["results"])
        total = p + f + n
        status_icon = "🔴" if f > 0 else ("🟢" if n == 0 else "🟡")

        header = (
            f"{status_icon} **{insp['name']}** &nbsp;·&nbsp; "
            f"{insp.get('checklist_name', '—')} &nbsp;·&nbsp; "
            f"{insp.get('inspection_date', '')}"
        )

        with st.expander(header, expanded=False):
            # Summary row
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Fields", total)
            m2.metric("🟢 Pass", p)
            m3.metric("🔴 Fail", f)
            m4.metric("⚪ Not Checked", n)

            st.markdown("---")

            # Field-by-field breakdown per template
            for tmpl_id, field_results in insp["results"].items():
                if not field_results:
                    continue

                tmpl_name = tmpl_name_map.get(tmpl_id, f"*(deleted – {tmpl_id[:8]}…)*")
                st.markdown(f"**{tmpl_name}**")

                h1, h2 = st.columns([4, 2])
                h1.markdown("**Field**")
                h2.markdown("**Result**")

                for fname, fval in field_results.items():
                    c1, c2 = st.columns([4, 2])
                    c1.markdown(fname)
                    c2.markdown(_BADGE.get(fval, fval))

                st.markdown("")


if __name__ == "__main__":
    main()
