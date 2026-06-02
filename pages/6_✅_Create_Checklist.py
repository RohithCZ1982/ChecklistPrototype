"""
Create Checklist – define a named checklist by selecting which templates belong to it.
"""

import streamlit as st

from config import APP_ICON, APP_TITLE
from modules.checklist_manager import (
    create_checklist,
    edit_checklist,
    get_all_checklists,
    remove_checklist,
)
from modules.template_manager import get_all_templates

st.set_page_config(
    page_title=f"Create Checklist – {APP_TITLE}", page_icon="✅", layout="wide"
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


# ─── Create tab ───────────────────────────────────────────────────────────────

def _create_tab():
    st.subheader("➕ New Checklist")

    templates = get_all_templates()
    if not templates:
        st.info("No templates found. Create some in the Template Builder first.")
        return

    name = st.text_input(
        "Checklist Name *",
        placeholder="e.g. Site Investigation Report",
        key="new_cl_name",
    )
    desc = st.text_area(
        "Description",
        placeholder="What this checklist covers…",
        height=80,
        key="new_cl_desc",
    )

    st.markdown("---")
    st.markdown("#### Select Templates")
    st.caption("Check the templates that belong to this checklist.")

    selected_ids: list[str] = []
    for tmpl in templates:
        checked = st.checkbox(
            f"**{tmpl['name']}**",
            key=f"new_cl_tmpl_{tmpl['id']}",
            help=tmpl.get("description") or "",
        )
        if tmpl.get("description"):
            st.caption(f"  {tmpl['description']}")
        if checked:
            selected_ids.append(tmpl["id"])

    st.markdown("---")
    if st.button("💾 Save Checklist", type="primary", use_container_width=True, key="save_cl"):
        if not name.strip():
            st.error("Checklist name is required.")
        elif not selected_ids:
            st.error("Select at least one template.")
        else:
            try:
                cid = create_checklist(name.strip(), desc.strip(), selected_ids)
                st.success(f"Checklist **{name}** saved! ({len(selected_ids)} template(s))")
            except Exception as e:
                st.error(f"Failed to save checklist: {e}")


# ─── Edit / Delete tab ────────────────────────────────────────────────────────

def _edit_tab():
    st.subheader("✏️ Edit / Delete Checklist")

    checklists = get_all_checklists()
    if not checklists:
        st.info("No checklists yet. Create one first.")
        return

    templates = get_all_templates()
    if not templates:
        st.info("No templates found.")
        return

    names = [c["name"] for c in checklists]
    selected_name = st.selectbox("Select checklist", names, key="edit_cl_select")
    cl = next((c for c in checklists if c["name"] == selected_name), None)
    if not cl:
        return

    # Reset state when checklist changes
    if st.session_state.get("edit_cl_last_id") != cl["id"]:
        st.session_state["edit_cl_last_id"] = cl["id"]

    new_name = st.text_input("Name", value=cl["name"], key=f"edit_cl_name_{cl['id']}")
    new_desc = st.text_area(
        "Description", value=cl.get("description", ""), height=80, key=f"edit_cl_desc_{cl['id']}"
    )

    st.markdown("---")
    st.markdown("#### Templates")

    selected_ids: list[str] = []
    for tmpl in templates:
        checked = st.checkbox(
            f"**{tmpl['name']}**",
            value=tmpl["id"] in cl["template_ids"],
            key=f"edit_cl_tmpl_{cl['id']}_{tmpl['id']}",
            help=tmpl.get("description") or "",
        )
        if tmpl.get("description"):
            st.caption(f"  {tmpl['description']}")
        if checked:
            selected_ids.append(tmpl["id"])

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Update Checklist", type="primary", use_container_width=True, key="upd_cl"):
            if not new_name.strip():
                st.error("Name is required.")
            elif not selected_ids:
                st.error("Select at least one template.")
            else:
                edit_checklist(cl["id"], new_name.strip(), new_desc.strip(), selected_ids)
                st.success("Checklist updated!")
                st.rerun()
    with col2:
        with st.popover("🗑️ Delete Checklist", use_container_width=True):
            st.warning(
                f"Permanently delete checklist **{cl['name']}**?\n\n"
                "Saved inspection records that reference this checklist are not affected. "
                "This cannot be undone."
            )
            if st.button(
                "Yes, delete permanently",
                key="confirm_del_cl",
                type="primary",
                use_container_width=True,
            ):
                remove_checklist(cl["id"])
                st.success("Deleted.")
                st.rerun()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _require_auth()
    _sidebar()

    st.title("✅ Create Checklist")
    st.markdown(
        "Group templates into a named checklist. "
        "Use the **View Checklist** page to load and review them."
    )

    tab_create, tab_edit = st.tabs(["➕ Create", "✏️ Edit / Delete"])
    with tab_create:
        _create_tab()
    with tab_edit:
        _edit_tab()


if __name__ == "__main__":
    main()
