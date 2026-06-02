"""Search & Query – global semantic + keyword search with RAG Q&A."""

import streamlit as st

from config import APP_ICON, APP_TITLE
from modules.database import list_documents
from modules.search_engine import document_similarity_matrix, global_search, rag_answer
from utils.helpers import confidence_color, truncate

st.set_page_config(
    page_title=f"Search – {APP_TITLE}", page_icon="🔍", layout="wide"
)

_CONF_EMOJI = {"green": "🟢", "orange": "🟡", "red": "🔴"}


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


# ─── Search tab ───────────────────────────────────────────────────────────────

def _search_tab():
    st.subheader("🔎 Global Document Search")

    docs = list_documents(status="processed")
    if not docs:
        st.info("No processed documents available.")
        return

    # ── Query input ───────────────────────────────────────────────────────────
    query = st.text_input(
        "Search query",
        placeholder="e.g. payment terms, invoice date, employee benefits…",
        key="search_query",
    )

    col_a, col_b, col_c, col_d = st.columns([2, 2, 1, 1])
    with col_a:
        mode = st.selectbox("Search mode", ["both", "semantic", "keyword"], key="search_mode")
    with col_b:
        doc_options = {f"{d['filename']} ({d['upload_date'][:10]})": d["id"] for d in docs}
        selected_labels = st.multiselect(
            "Filter by document (all if empty)", list(doc_options.keys()), key="search_docs"
        )
        doc_ids = [doc_options[l] for l in selected_labels] if selected_labels else None
    with col_c:
        top_k = st.number_input("Max results", 1, 30, 10, key="search_k")
    with col_d:
        min_conf = st.slider("Min confidence", 0.0, 1.0, 0.2, 0.05, key="search_min_conf")

    if not query.strip():
        st.markdown("*Enter a query above to search across all indexed documents.*")
        return

    if st.button("🔍 Search", type="primary", use_container_width=True, key="run_search"):
        with st.spinner("Searching…"):
            results = global_search(
                query,
                doc_ids=doc_ids,
                top_k=top_k,
                search_mode=mode,
                min_confidence=min_conf,
            )
            st.session_state["search_results"] = results
            st.session_state["last_query"] = query

    results = st.session_state.get("search_results", [])
    last_query = st.session_state.get("last_query", "")

    if not results and last_query:
        st.warning(f"No results found for **{last_query}**.")
        return

    if results:
        st.markdown(f"**{len(results)} result(s) for:** `{last_query}`")
        st.markdown("---")

        for i, r in enumerate(results, 1):
            conf = r.get("confidence", 0)
            badge = _CONF_EMOJI.get(confidence_color(conf), "⚪")
            with st.container():
                col_l, col_r = st.columns([5, 1])
                with col_l:
                    st.markdown(
                        f"**{i}. {r.get('filename', 'Unknown')}**  ·  "
                        f"Page {r.get('page_number', '?')}  ·  "
                        f"{badge} {conf:.0%} ({r.get('source','?')})"
                    )
                    snippet = r.get("snippet") or truncate(r.get("text", ""), 350)
                    st.markdown(f"> {snippet}")
                with col_r:
                    with st.expander("Full text"):
                        st.write(r.get("text", ""))
                st.divider()


# ─── Q&A tab ─────────────────────────────────────────────────────────────────

def _qa_tab():
    st.subheader("🤖 Ask a Question (RAG)")
    st.caption("Uses semantic search + LLM to answer from your documents. Requires OpenAI API key.")

    docs = list_documents(status="processed")
    if not docs:
        st.info("No processed documents available.")
        return

    question = st.text_input(
        "Your question",
        placeholder="What are the payment terms in the contract?",
        key="qa_question",
    )

    doc_options = {f"{d['filename']}": d["id"] for d in docs}
    selected_labels = st.multiselect(
        "Limit to specific documents (all if empty)",
        list(doc_options.keys()),
        key="qa_docs",
    )
    doc_ids = [doc_options[l] for l in selected_labels] if selected_labels else None

    if st.button("💬 Ask", type="primary", use_container_width=True, key="run_qa"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Thinking…"):
                result = rag_answer(question, doc_ids=doc_ids)
                st.session_state["qa_result"] = result

    qa_result = st.session_state.get("qa_result")
    if qa_result:
        st.markdown("### Answer")
        st.markdown(qa_result.get("answer", "No answer generated."))

        sources = qa_result.get("sources", [])
        if sources:
            with st.expander(f"📄 Sources ({len(sources)} chunks)"):
                for s in sources:
                    st.markdown(
                        f"**{s.get('filename','?')}** — Page {s.get('page_number','?')} — "
                        f"{s.get('confidence',0):.0%} confidence"
                    )
                    st.markdown(f"> {truncate(s.get('text',''), 250)}")
                    st.divider()


# ─── Similarity tab ───────────────────────────────────────────────────────────

def _similarity_tab():
    st.subheader("🔗 Document Similarity")
    st.caption("Pairwise Jaccard similarity matrix based on shared vocabulary.")

    docs = list_documents(status="processed")
    if len(docs) < 2:
        st.info("Need at least 2 processed documents.")
        return

    doc_map = {d["filename"]: d["id"] for d in docs}
    selected = st.multiselect(
        "Select documents to compare (2–8 recommended)",
        list(doc_map.keys()),
        default=list(doc_map.keys())[:4],
        key="sim_docs",
    )

    if len(selected) < 2:
        st.warning("Select at least 2 documents.")
        return

    if st.button("📊 Compute Similarity", type="primary", key="run_sim"):
        doc_ids = [doc_map[n] for n in selected]
        with st.spinner("Computing…"):
            matrix = document_similarity_matrix(doc_ids)
            st.session_state["sim_matrix"] = matrix
            st.session_state["sim_names"] = {d["id"]: d["filename"] for d in docs}

    matrix = st.session_state.get("sim_matrix")
    if not matrix:
        return

    names_map = st.session_state.get("sim_names", {})
    import pandas as pd

    doc_ids_ord = list(matrix.keys())
    labels = [names_map.get(did, did[:8]) for did in doc_ids_ord]
    data = [[matrix[a].get(b, 0) for b in doc_ids_ord] for a in doc_ids_ord]
    df = pd.DataFrame(data, index=labels, columns=labels)
    st.dataframe(df.style.background_gradient(cmap="Blues", vmin=0, vmax=1), use_container_width=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _require_auth()
    _sidebar()

    st.title("🔍 Search & Query")
    st.markdown("Search across all indexed documents using semantic similarity, keywords, or ask questions.")

    tab_search, tab_qa, tab_sim = st.tabs(["🔎 Search", "🤖 Q&A", "🔗 Similarity"])
    with tab_search:
        _search_tab()
    with tab_qa:
        _qa_tab()
    with tab_sim:
        _similarity_tab()


if __name__ == "__main__":
    main()
