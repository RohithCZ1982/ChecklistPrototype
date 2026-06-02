"""
Template Builder – create templates, define fields, and generate
structured output by pulling relevant content from indexed documents.
"""

import json
import re

import pandas as pd
import streamlit as st

from config import APP_ICON, APP_TITLE
from modules.database import list_documents
from modules.search_engine import global_search
from modules.template_manager import (
    create_template,
    edit_template,
    generate_template_output,
    get_all_templates,
    get_results_history,
    load_template,
    remove_template,
)
from utils.helpers import confidence_color, is_markdown_table, truncate

st.set_page_config(
    page_title=f"Template Builder – {APP_TITLE}", page_icon="📋", layout="wide"
)

_SEARCH_MODES = ["both", "semantic", "keyword"]
_CONFIDENCE_EMOJI = {
    "green": "🟢",
    "orange": "🟡",
    "red": "🔴",
}


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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _render_table_if_detected(text: str) -> bool:
    """
    Detect a markdown-style table in text and render it as a dataframe.
    Returns True if a table was found and rendered, False otherwise.
    """
    lines = [l for l in text.strip().split("\n") if l.strip()]
    pipe_lines = [l for l in lines if "|" in l]
    if len(pipe_lines) < 2:
        return False
    try:
        data_rows = []
        for line in pipe_lines:
            if re.match(r"^\s*\|[-:\s|]+\|\s*$", line):
                continue  # skip separator row
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells:
                data_rows.append(cells)
        if len(data_rows) < 2:
            return False
        max_cols = max(len(r) for r in data_rows)
        data_rows = [r + [""] * (max_cols - len(r)) for r in data_rows]
        df = pd.DataFrame(data_rows[1:], columns=data_rows[0])
        st.dataframe(df, use_container_width=True, hide_index=True)
        return True
    except Exception:
        return False


# ─── Field search callback ────────────────────────────────────────────────────

def _search_for_field_name(key_prefix: str, i: int) -> None:
    """on_change callback: runs the search whenever the field name widget changes."""
    name = st.session_state.get(f"{key_prefix}_fname_{i}", "").strip()
    results_key = f"{key_prefix}_field_results_{i}"
    error_key = f"{key_prefix}_field_search_err_{i}"
    # Clear previous state
    st.session_state.pop(error_key, None)
    if not name:
        st.session_state.pop(results_key, None)
        return
    try:
        hits = global_search(name, top_k=3, search_mode="both", min_confidence=0.1)
        st.session_state[results_key] = hits          # [] = searched, no matches
    except Exception as e:
        st.session_state[results_key] = []            # treat as empty
        st.session_state[error_key] = str(e)


# ─── Field editor ─────────────────────────────────────────────────────────────

def _render_field_editor(existing_fields: list | None = None, key_prefix: str = "create") -> list:
    """
    Show a dynamic form for adding/editing template fields.
    When a field name is entered, searches indexed documents and displays
    matching passages in a table so the user can copy text into Description.
    Returns the final list of field dicts.
    """
    _fields_key = f"{key_prefix}_fields"
    if _fields_key not in st.session_state:
        st.session_state[_fields_key] = existing_fields or []

    fields = st.session_state[_fields_key]

    st.markdown("#### Fields / Keywords")
    st.caption(
        "Enter a field name — matching content from your documents appears below. "
        "Copy relevant text and paste it into the **Description** column."
    )

    col_a, col_b, col_c, col_d = st.columns([3, 4, 2, 1])
    col_a.markdown("**Field Name**")
    col_b.markdown("**Description / Hint**")
    col_c.markdown("**Search Mode**")
    col_d.markdown("")

    updated_fields = []

    for i, f in enumerate(fields):
        ca, cb, cc, cd = st.columns([3, 4, 2, 1])

        _name_key = f"{key_prefix}_fname_{i}"
        name = ca.text_input(
            "", value=f.get("name", ""), key=_name_key,
            label_visibility="collapsed", placeholder="e.g. CBR Value",
            on_change=_search_for_field_name, args=(key_prefix, i),
        )

        # For description: if a table was staged via "Use as Description", write it
        # into the widget key BEFORE instantiation (pre-instantiation writes are allowed).
        _desc_key = f"{key_prefix}_fdesc_{i}"
        _desc_pending_key = f"{key_prefix}_fdesc_pending_{i}"
        if _desc_pending_key in st.session_state:
            st.session_state[_desc_key] = st.session_state.pop(_desc_pending_key)
        desc = cb.text_area(
            "", value=f.get("description", ""), key=_desc_key,
            label_visibility="collapsed", placeholder="Paste text or table from results below…",
            height=100,
        )
        mode = cc.selectbox(
            "", _SEARCH_MODES,
            index=_SEARCH_MODES.index(f.get("search_mode", "both")),
            key=f"{key_prefix}_fmode_{i}", label_visibility="collapsed",
        )

        if cd.button("✕", key=f"{key_prefix}_fdel_{i}", help="Remove this field"):
            for _k in [
                f"{key_prefix}_field_results_{i}",
                f"{key_prefix}_field_search_err_{i}",
                _name_key,
                _desc_key,
                _desc_pending_key,
                f"{key_prefix}_fmode_{i}",
            ]:
                st.session_state.pop(_k, None)
        else:
            updated_fields.append({"name": name, "description": desc, "search_mode": mode})

            # Display search results (populated by on_change callback)
            _results_key = f"{key_prefix}_field_results_{i}"
            _error_key = f"{key_prefix}_field_search_err_{i}"

            if name.strip() and _results_key not in st.session_state:
                st.caption("↵ Press **Enter** or **Tab** to search documents.")
            elif st.session_state.get(_error_key):
                st.warning(f"Search error: {st.session_state[_error_key]}")
            elif _results_key in st.session_state and not st.session_state[_results_key]:
                st.caption("🔍 No matching content found — ensure documents are processed.")

            hits = st.session_state.get(_results_key, [])
            if hits and name.strip():
                st.caption(f"Top {len(hits)} result(s) — use a result or paste its text into **Description**")
                for j, r in enumerate(hits[:3]):
                    conf = r.get("confidence", 0)
                    badge = _CONFIDENCE_EMOJI.get(confidence_color(conf), "⚪")
                    full_text = r.get("text", "")
                    snippet = r.get("snippet") or full_text
                    is_table = is_markdown_table(full_text)

                    st.markdown(
                        f"{badge} **{r.get('filename', 'Unknown')}** &nbsp;·&nbsp; "
                        f"Page {r.get('page_number', '?')} &nbsp;·&nbsp; {conf:.0%}"
                        + (" &nbsp;·&nbsp; 📊 *Table*" if is_table else "")
                    )

                    if is_table:
                        # Render the table immediately (no expander needed for preview)
                        _render_table_if_detected(full_text)
                        if st.button(
                            "📌 Use this table as Description",
                            key=f"{key_prefix}_use_tbl_{i}_{j}",
                        ):
                            # Stage the value; consumed before the widget is created
                            # on the next render to avoid the post-instantiation error.
                            st.session_state[f"{key_prefix}_fdesc_pending_{i}"] = full_text
                            st.rerun()
                    else:
                        st.markdown(f"> {truncate(snippet, 200)}")
                        with st.expander("📖 Full text"):
                            if not _render_table_if_detected(full_text):
                                st.text(full_text)

                    if j < len(hits[:3]) - 1:
                        st.divider()

    st.session_state[_fields_key] = updated_fields

    if st.button("➕ Add Field", key=f"{key_prefix}_add_field_btn"):
        st.session_state[_fields_key].append({"name": "", "description": "", "search_mode": "both"})
        st.rerun()

    return st.session_state[_fields_key]


# ─── Create / Edit form ───────────────────────────────────────────────────────

def _create_template_tab():
    st.subheader("➕ Create New Template")
    name = st.text_input("Template Name *", placeholder="e.g. Contract Summary", key="new_tmpl_name")
    desc = st.text_area("Description", placeholder="What this template extracts…", height=80, key="new_tmpl_desc")

    _render_field_editor([], key_prefix="create")

    fields = [f for f in st.session_state.get("create_fields", []) if f.get("name", "").strip()]
    st.markdown("---")
    if st.button("💾 Save Template", type="primary", use_container_width=True, key="save_new_tmpl"):
        if not name.strip():
            st.error("Template name is required.")
        elif not fields:
            st.error("Add at least one field with a name.")
        else:
            try:
                tid = create_template(name.strip(), desc.strip(), fields)
                st.success(f"Template **{name}** created! (ID: {tid[:8]}…)")
                st.session_state["create_fields"] = []
                st.rerun()
            except Exception as e:
                st.error(f"Failed to create template: {e}")


def _edit_template_tab():
    st.subheader("✏️ Edit Template")
    templates = get_all_templates()
    if not templates:
        st.info("No templates yet. Create one first.")
        return

    names = [t["name"] for t in templates]
    selected_name = st.selectbox("Select template to edit", names, key="edit_select")
    tmpl = next((t for t in templates if t["name"] == selected_name), None)
    if not tmpl:
        return

    new_name = st.text_input("Name", value=tmpl["name"], key=f"edit_name_{tmpl['id']}")
    new_desc = st.text_area("Description", value=tmpl.get("description", ""), height=80, key=f"edit_desc_{tmpl['id']}")

    if st.session_state.get("edit_last_tmpl_id") != tmpl["id"]:
        st.session_state["edit_fields"] = list(tmpl.get("fields", []))
        st.session_state["edit_last_tmpl_id"] = tmpl["id"]
    _render_field_editor(tmpl.get("fields", []), key_prefix="edit")
    fields = st.session_state.get("edit_fields", [])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Update Template", type="primary", use_container_width=True, key="upd_tmpl"):
            edit_template(tmpl["id"], new_name.strip(), new_desc.strip(), fields)
            st.success("Template updated!")
            st.rerun()
    with col2:
        if st.button("🗑️ Delete Template", type="secondary", use_container_width=True, key="del_tmpl"):
            remove_template(tmpl["id"])
            st.success("Deleted.")
            st.rerun()


# ─── Generate output ─────────────────────────────────────────────────────────

def _generate_tab():
    st.subheader("⚡ Generate Template Output")

    templates = get_all_templates()
    if not templates:
        st.info("No templates yet. Create one first.")
        return

    docs = list_documents(status="processed")
    if not docs:
        st.info("No processed documents. Upload and process some first.")
        return

    # Template picker
    tmpl_names = [t["name"] for t in templates]
    selected_name = st.selectbox("Template", tmpl_names, key="gen_tmpl_select")
    tmpl = next((t for t in templates if t["name"] == selected_name), None)

    st.markdown(f"**Fields:** {', '.join(f['name'] for f in tmpl['fields'])}")
    if tmpl.get("description"):
        st.caption(tmpl["description"])

    # Document picker
    st.markdown("**Documents to search** (leave empty = all)")
    doc_options = {f"{d['filename']} ({d['upload_date'][:10]})": d["id"] for d in docs}
    selected_doc_labels = st.multiselect(
        "Select documents", list(doc_options.keys()), key="gen_doc_select"
    )
    selected_doc_ids = [doc_options[l] for l in selected_doc_labels] if selected_doc_labels else None

    col_a, col_b = st.columns(2)
    with col_a:
        top_k = st.slider("Max hits per field", 1, 10, 5)
    with col_b:
        use_llm = st.toggle(
            "Use LLM to synthesize answers",
            value=False,
            help="Requires OPENAI_API_KEY",
        )

    if st.button("🚀 Generate Output", type="primary", use_container_width=True, key="gen_run"):
        with st.spinner("Searching documents and generating output…"):
            try:
                output = generate_template_output(
                    template_id=tmpl["id"],
                    doc_ids=selected_doc_ids,
                    top_k=top_k,
                    use_llm=use_llm,
                )
                st.session_state["last_template_output"] = output
            except Exception as e:
                st.error(f"Generation failed: {e}")
                import traceback
                with st.expander("Details"):
                    st.code(traceback.format_exc())
                return

    # ── Display results ───────────────────────────────────────────────────────
    output = st.session_state.get("last_template_output")
    if not output:
        return

    if output.get("template", {}).get("name") != selected_name:
        return  # stale result from different template

    st.markdown("---")
    st.markdown(f"## Results: {output['template']['name']}")
    st.caption(f"Result ID: {output.get('result_id','')[:8]}…")

    for fname, fdata in output.get("fields", {}).items():
        conf = fdata.get("top_confidence", 0)
        color = confidence_color(conf)
        badge = _CONFIDENCE_EMOJI.get(color, "⚪")
        hits = fdata.get("hits", [])

        with st.expander(
            f"{badge} **{fname}** — Confidence: {conf:.0%}  |  {len(hits)} hit(s)",
            expanded=True,
        ):
            if fdata.get("synthesized_answer"):
                st.markdown("**🤖 Synthesized Answer**")
                answer = st.text_area(
                    "Edit if needed:",
                    value=fdata["synthesized_answer"],
                    key=f"synth_{fname}",
                    height=100,
                )
                st.markdown("---")

            if hits:
                st.markdown("**📄 Supporting Evidence**")
                for i, hit in enumerate(hits[:5], 1):
                    hit_conf = hit.get("confidence", 0)
                    hit_badge = _CONFIDENCE_EMOJI.get(confidence_color(hit_conf), "⚪")
                    st.markdown(
                        f"{hit_badge} **Hit {i}** — "
                        f"Doc: `{hit.get('document_id','')[:8]}…`  |  "
                        f"Page: {hit.get('page_number', '?')}  |  "
                        f"Confidence: {hit_conf:.0%}  |  "
                        f"Source: {hit.get('source','semantic')}"
                    )
                    st.markdown(
                        f"> {truncate(hit.get('text',''), 300)}"
                    )
            else:
                st.warning("No relevant content found for this field.")

    # ── Export shortcuts ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Export this result →** go to the [Export page](5_📤_Export)")


# ─── History tab ─────────────────────────────────────────────────────────────

def _history_tab():
    st.subheader("📜 Result History")
    templates = get_all_templates()
    if not templates:
        st.info("No templates yet.")
        return

    names = [t["name"] for t in templates]
    sel = st.selectbox("Template", names, key="hist_select")
    tmpl = next((t for t in templates if t["name"] == sel), None)
    if not tmpl:
        return

    history = get_results_history(tmpl["id"])
    if not history:
        st.info("No results generated yet for this template.")
        return

    for r in history:
        status = "✅ Approved" if r.get("approved") else "⏳ Pending approval"
        with st.expander(
            f"{status}  —  {r.get('generated_date','')[:19]}  |  "
            f"{len(r.get('document_ids',[]))} doc(s)",
            expanded=False,
        ):
            fields_data = r.get("results", {})
            for fname, fdata in fields_data.items():
                conf = fdata.get("top_confidence", 0)
                st.markdown(
                    f"**{fname}** — {confidence_color(conf)} ({conf:.0%})\n\n"
                    f"> {truncate(fdata.get('synthesized_answer',''), 250)}"
                )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _require_auth()
    _sidebar()

    st.title("📋 Template Builder")
    st.markdown(
        "Create templates with field definitions. "
        "Run them to automatically extract structured content from your documents."
    )

    tab_create, tab_edit, tab_generate, tab_history = st.tabs(
        ["➕ Create", "✏️ Edit", "⚡ Generate", "📜 History"]
    )
    with tab_create:
        _create_template_tab()
    with tab_edit:
        _edit_template_tab()
    with tab_generate:
        _generate_tab()
    with tab_history:
        _history_tab()


if __name__ == "__main__":
    main()
