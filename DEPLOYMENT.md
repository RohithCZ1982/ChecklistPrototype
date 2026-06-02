# Deployment Guide

Two hosting paths for this app: a quick demo deployment on Streamlit Community Cloud, and a production-grade setup on Render + Supabase.

---

## Option A — Streamlit Community Cloud (demo / no persistence)

Best for: showcasing the app. Uploaded documents and extracted data do **not** persist across restarts.

### Prerequisites

- GitHub account with this repo pushed to it
- Streamlit account at [share.streamlit.io](https://share.streamlit.io)

### Steps

1. **Push the repo to GitHub** (public or private).

2. **Log in to Streamlit Community Cloud** and click **New app**.

3. Set:
   - Repository: your GitHub repo
   - Branch: `main`
   - Main file path: `app.py`

4. Under **Advanced settings → Secrets**, add your environment variables in TOML format:
   ```toml
   OPENAI_API_KEY = "sk-..."
   APP_USERNAME = "admin"
   APP_PASSWORD = "yourpassword"
   SECRET_KEY = "a-random-secret"
   ```
   These map to what `config.py` reads from `.env`.

5. Click **Deploy**. The app will be live at `https://<your-app>.streamlit.app`.

### Limitations

- The `data/` directory (SQLite, ChromaDB, uploads) is ephemeral — it resets on every restart or redeploy.
- Apps sleep after ~15 minutes of inactivity and take ~30 seconds to wake.
- 1 GB RAM limit; large embedding models may crash the app.

---

## Option B — Render + Supabase (persistent, production-grade)

Best for: real use where uploaded documents and vectors must survive restarts.

This path replaces:
- `data/metadata.db` (SQLite) → **Supabase Postgres**
- `data/uploads/` (local files) → **Supabase Storage**
- `data/chroma_db/` (ChromaDB) → **Qdrant Cloud** (free 1 GB tier)
- App server → **Render Web Service**

---

### Part 1 — Supabase (database + file storage)

#### 1.1 Create a project

1. Sign up at [supabase.com](https://supabase.com) and create a new project.
2. Note your **Project URL** and **anon/service_role API keys** from *Project Settings → API*.
3. Note your **Database connection string** from *Project Settings → Database → Connection string → Python*.

#### 1.2 Create the schema

Run the following in the Supabase **SQL Editor** (mirrors the SQLite schema in `modules/database.py`):

```sql
create extension if not exists "uuid-ossp";

create table if not exists documents (
  id            text primary key,
  filename      text not null,
  file_hash     text unique not null,
  file_type     text,
  file_size     bigint,
  page_count    int,
  upload_date   timestamptz default now(),
  status        text default 'pending',
  doc_metadata  jsonb default '{}'
);

create table if not exists chunks (
  id            text primary key,
  document_id   text references documents(id) on delete cascade,
  chunk_index   int,
  content       text,
  page_number   int,
  chunk_metadata jsonb default '{}'
);

create table if not exists templates (
  id            text primary key,
  name          text not null,
  description   text,
  fields        jsonb default '[]',
  created_date  timestamptz default now(),
  updated_date  timestamptz default now()
);

create table if not exists extractions (
  id            text primary key,
  template_id   text references templates(id) on delete cascade,
  document_id   text references documents(id) on delete cascade,
  results       jsonb default '{}',
  created_date  timestamptz default now()
);

-- Full-text search index (replaces SQLite FTS5)
create index if not exists chunks_content_fts
  on chunks using gin(to_tsvector('english', content));
```

#### 1.3 Create a storage bucket

1. Go to *Storage → New bucket*, name it `uploads`, set it to **private**.
2. The app will upload files here instead of `data/uploads/`.

---

### Part 2 — Qdrant Cloud (vector store)

1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io) and create a free cluster.
2. Note the **cluster URL** and **API key**.

---

### Part 3 — Adapt the code

Three modules need updating. The changes are isolated — pages do not need to change.

#### 3.1 `modules/database.py` — swap SQLite for Supabase Postgres

Replace `sqlite3` calls with `psycopg2` (or the `supabase-py` client). Key changes:

```python
# requirements.txt additions
# supabase==2.*
# psycopg2-binary

import os
from supabase import create_client

def _client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Example: replace sqlite insert with supabase upsert
def add_document(doc: dict):
    _client().table("documents").upsert(doc).execute()

# Full-text search (replaces FTS5 MATCH)
def search_chunks_keyword(query: str, limit: int = 20):
    sql = f"""
        select *, ts_rank(to_tsvector('english', content),
                          plainto_tsquery('english', %s)) as rank
        from chunks
        where to_tsvector('english', content) @@ plainto_tsquery('english', %s)
        order by rank desc limit %s
    """
    # execute via psycopg2 connection or supabase rpc
```

#### 3.2 `modules/vector_store.py` — swap ChromaDB for Qdrant

```python
# requirements.txt addition: qdrant-client

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import os, uuid

@st.cache_resource
def _qdrant():
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )

COLLECTION = "document_chunks"
VECTOR_DIM = 384  # matches all-MiniLM-L6-v2

def ensure_collection():
    client = _qdrant()
    if COLLECTION not in [c.name for c in client.get_collections().collections]:
        client.create_collection(COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE))

def index_chunks(chunks: list[dict], embeddings: list[list[float]]):
    ensure_collection()
    points = [
        PointStruct(id=str(uuid.uuid4()), vector=emb,
                    payload={k: v for k, v in chunk.items()
                             if isinstance(v, (str, int, float, bool))})
        for chunk, emb in zip(chunks, embeddings)
    ]
    _qdrant().upsert(collection_name=COLLECTION, points=points)

def search(query_embedding: list[float], n_results: int = 10, filters: dict = None):
    hits = _qdrant().search(COLLECTION, query_embedding, limit=n_results)
    return [{"content": h.payload.get("content"), "metadata": h.payload,
             "distance": 1 - h.score} for h in hits]
```

#### 3.3 `modules/document_processor.py` — swap local file save for Supabase Storage

```python
from supabase import create_client
import os

def _storage():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]).storage

def save_upload(file_bytes: bytes, filename: str, doc_id: str) -> str:
    path = f"{doc_id}/{filename}"
    _storage().from_("uploads").upload(path, file_bytes)
    return path   # store this path in documents.file_path column

def load_upload(path: str) -> bytes:
    return _storage().from_("uploads").download(path)
```

---

### Part 4 — Environment variables

Create a `.env` file locally (already gitignored) and add the new keys:

```dotenv
# Existing
OPENAI_API_KEY=sk-...
APP_USERNAME=admin
APP_PASSWORD=yourpassword
SECRET_KEY=a-random-secret

# New
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
DATABASE_URL=postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres
QDRANT_URL=https://xxxx.qdrant.io
QDRANT_API_KEY=your-qdrant-key
```

Update `config.py` to read these new variables alongside the existing ones.

---

### Part 5 — Render Web Service

#### 5.1 Create the service

1. Sign up at [render.com](https://render.com) and click **New → Web Service**.
2. Connect your GitHub repo.
3. Set:
   - **Environment**: Python 3
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

#### 5.2 Add environment variables

In *Environment → Environment Variables*, add all keys from the `.env` block above. Do **not** commit `.env` to git.

#### 5.3 Free tier notes

- Render free web services spin down after 15 minutes of inactivity (same as Streamlit Community Cloud).
- Upgrade to the **Starter** plan ($7/month) to keep the service always-on.
- Supabase and Qdrant free tiers are always-on regardless.

---

## Side-by-side comparison

| | Streamlit Community Cloud | Render + Supabase + Qdrant |
|---|---|---|
| Cost | Free | Free (with spin-down) or ~$7/mo always-on |
| Persistence | None (ephemeral) | Full |
| Setup time | ~10 minutes | ~2–4 hours (code changes required) |
| RAM | 1 GB | 512 MB free / 2 GB paid |
| Best for | Demo / prototype | Ongoing real use |
| Code changes needed | None | `database.py`, `vector_store.py`, `document_processor.py` |
