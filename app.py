"""
AI Document Intelligence – Main entry point.

Run with:  streamlit run app.py
"""

import hashlib

import streamlit as st

from config import APP_ICON, APP_TITLE, AUTH_PASSWORD, AUTH_USERNAME
from modules.database import get_stats, init_db

# ─── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": f"### {APP_ICON} {APP_TITLE}\nIntelligent Document Analysis Platform"},
)

# Initialize DB tables on every cold start
init_db()


# ─── Styles ───────────────────────────────────────────────────────────────────

def _inject_css(dark: bool = False) -> None:
    bg = "#0E1117" if dark else "#FFFFFF"
    card_bg = "#1C2333" if dark else "#F0F2F6"
    text = "#FAFAFA" if dark else "#0E1117"
    accent = "#4F8EF7"

    st.markdown(
        f"""
<style>
  body {{ background-color: {bg}; color: {text}; }}

  .main-header {{
      background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
      padding: 2rem 2.5rem;
      border-radius: 12px;
      color: white;
      margin-bottom: 1.5rem;
  }}
  .main-header h1 {{ margin: 0; font-size: 2.2rem; }}
  .main-header p  {{ margin: 0.4rem 0 0; opacity: 0.85; font-size: 1.05rem; }}

  .metric-card {{
      background: {card_bg};
      padding: 1.2rem 1.5rem;
      border-radius: 10px;
      border-left: 5px solid {accent};
  }}

  div[data-testid="metric-container"] {{
      background: {card_bg};
      border: 1px solid #DDE0E7;
      border-radius: 10px;
      padding: 1rem;
  }}

  .stButton > button {{
      border-radius: 8px;
      font-weight: 600;
  }}

  .confidence-high  {{ color: #22c55e; font-weight: 700; }}
  .confidence-mid   {{ color: #f59e0b; font-weight: 700; }}
  .confidence-low   {{ color: #ef4444; font-weight: 700; }}
</style>
""",
        unsafe_allow_html=True,
    )


# ─── Auth ─────────────────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _check_auth(username: str, password: str) -> bool:
    return username == AUTH_USERNAME and _hash(password) == _hash(AUTH_PASSWORD)


def _login_page() -> None:
    _inject_css()
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(
            f"""
<div class="main-header" style="text-align:center;">
  <h1>{APP_ICON} {APP_TITLE}</h1>
  <p>Intelligent Document Analysis &amp; Template Generation Platform</p>
</div>
""",
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            if _check_auth(username, password):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("Invalid credentials. Default: admin / admin123")

        st.caption("ℹ️ Default credentials: **admin** / **admin123**")


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"## {APP_ICON} {APP_TITLE}")
        st.caption(f"v{__import__('config').APP_VERSION}")
        st.markdown(f"👤 Logged in as **{st.session_state.get('username', 'admin')}**")
        st.divider()

        # Dark-mode toggle
        dark = st.toggle(
            "🌙 Dark Mode",
            value=st.session_state.get("dark_mode", False),
            key="dark_mode_toggle",
        )
        st.session_state["dark_mode"] = dark

        st.divider()
        st.markdown("### Navigation")
        st.page_link("app.py",                              label="🏠 Home")
        st.page_link("pages/1_📊_Dashboard.py",             label="📊 Dashboard")
        st.page_link("pages/2_📄_Document_Processor.py",    label="📄 Document Processor")
        st.page_link("pages/3_📋_Template_Builder.py",      label="📋 Template Builder")
        st.page_link("pages/4_🔍_Search.py",                label="🔍 Search & Query")
        st.page_link("pages/5_📤_Export.py",                label="📤 Export")
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ─── Home ─────────────────────────────────────────────────────────────────────

def _home_page() -> None:
    dark = st.session_state.get("dark_mode", False)
    _inject_css(dark)
    _render_sidebar()

    st.markdown(
        f"""
<div class="main-header">
  <h1>{APP_ICON} {APP_TITLE}</h1>
  <p>Intelligent Document Analysis &amp; Template Generation Platform</p>
</div>
""",
        unsafe_allow_html=True,
    )

    # Stats row
    stats = get_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📂 Documents",      stats["documents"])
    c2.metric("📑 Chunks Indexed", stats["chunks"])
    c3.metric("📋 Templates",      stats["templates"])
    c4.metric("🏷️ Entities",       stats["entities"])
    c5.metric("✅ Processed",      stats["processed"])

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 🚀 Quick Actions")
        st.page_link("pages/2_📄_Document_Processor.py",
                     label="Upload & Process Documents", icon="📄")
        st.page_link("pages/3_📋_Template_Builder.py",
                     label="Build or Run a Template", icon="📋")
        st.page_link("pages/4_🔍_Search.py",
                     label="Search Documents", icon="🔍")
        st.page_link("pages/5_📤_Export.py",
                     label="Export Results", icon="📤")

    with col_right:
        st.markdown("### ℹ️ About this App")
        st.markdown(
            """
This platform lets you:

- **Upload** PDFs, Word docs, TXT files, and images (OCR)
- **Index** documents with semantic embeddings (vector search)
- **Build Templates** to automatically extract structured information
- **Search** across all documents with semantic + keyword search
- **Export** results as JSON, Excel, or Word

**Tech stack:** Streamlit · ChromaDB · sentence-transformers ·
PyMuPDF · python-docx · SQLite · OpenAI (optional)
"""
        )


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if not st.session_state.get("authenticated", False):
        _login_page()
        return
    _home_page()


if __name__ == "__main__":
    main()
