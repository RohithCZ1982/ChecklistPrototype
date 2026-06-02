"""SQLite metadata store for documents, chunks, templates, entities, and results."""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import DB_PATH


# ─── Connection ───────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema ───────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they do not exist."""
    conn = get_connection()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            file_type   TEXT NOT NULL,
            file_size   INTEGER,
            title       TEXT,
            doc_type    TEXT,
            upload_date TEXT NOT NULL,
            processed_date TEXT,
            status      TEXT DEFAULT 'pending',
            chunk_count INTEGER DEFAULT 0,
            page_count  INTEGER DEFAULT 0,
            summary     TEXT,
            doc_hash    TEXT,
            version     INTEGER DEFAULT 1,
            metadata    TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id           TEXT PRIMARY KEY,
            document_id  TEXT NOT NULL,
            chunk_index  INTEGER NOT NULL,
            text         TEXT NOT NULL,
            page_number  INTEGER DEFAULT 1,
            char_start   INTEGER,
            char_end     INTEGER,
            created_date TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS templates (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL UNIQUE,
            description  TEXT,
            fields       TEXT NOT NULL,
            created_date TEXT NOT NULL,
            updated_date TEXT NOT NULL,
            created_by   TEXT DEFAULT 'admin'
        );

        CREATE TABLE IF NOT EXISTS template_results (
            id            TEXT PRIMARY KEY,
            template_id   TEXT NOT NULL,
            document_ids  TEXT,
            results       TEXT,
            generated_date TEXT,
            approved      INTEGER DEFAULT 0,
            notes         TEXT,
            FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS checklists (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL UNIQUE,
            description  TEXT,
            template_ids TEXT NOT NULL,
            created_date TEXT NOT NULL,
            updated_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inspections (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            checklist_id    TEXT NOT NULL,
            checklist_name  TEXT,
            inspection_date TEXT NOT NULL,
            results         TEXT NOT NULL,
            created_date    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entities (
            id           TEXT PRIMARY KEY,
            document_id  TEXT NOT NULL,
            chunk_id     TEXT,
            entity_type  TEXT NOT NULL,
            entity_text  TEXT NOT NULL,
            confidence   REAL DEFAULT 1.0,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            id UNINDEXED,
            document_id UNINDEXED,
            text,
            content='chunks',
            content_rowid='rowid'
        );
    """)

    conn.commit()
    conn.close()


# ─── Documents ────────────────────────────────────────────────────────────────

def add_document(
    filename: str,
    file_type: str,
    file_size: int,
    doc_hash: str,
    metadata: Optional[Dict] = None,
) -> str:
    doc_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        """INSERT INTO documents
           (id, filename, file_type, file_size, upload_date, status, doc_hash, metadata)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            doc_id, filename, file_type, file_size,
            datetime.utcnow().isoformat(),
            doc_hash,
            json.dumps(metadata or {}),
        ),
    )
    conn.commit()
    conn.close()
    return doc_id


def update_document(doc_id: str, **kwargs) -> None:
    if not kwargs:
        return
    conn = get_connection()
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [doc_id]
    conn.execute(f"UPDATE documents SET {cols} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def get_document(doc_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_documents(status: Optional[str] = None) -> List[Dict]:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM documents WHERE status = ? ORDER BY upload_date DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY upload_date DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document(doc_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


def find_document_by_hash(doc_hash: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM documents WHERE doc_hash = ?", (doc_hash,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Chunks ───────────────────────────────────────────────────────────────────

def add_chunks(document_id: str, chunks: List[Dict]) -> List[str]:
    """Bulk-insert chunks; returns list of generated chunk IDs."""
    conn = get_connection()
    chunk_ids = []
    now = datetime.utcnow().isoformat()
    rows = []
    for i, ch in enumerate(chunks):
        cid = str(uuid.uuid4())
        chunk_ids.append(cid)
        rows.append((
            cid, document_id, i,
            ch.get("text", ""),
            ch.get("page_number", 1),
            ch.get("char_start"),
            ch.get("char_end"),
            now,
        ))

    conn.executemany(
        """INSERT INTO chunks
           (id, document_id, chunk_index, text, page_number, char_start, char_end, created_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )

    # Update FTS index
    for cid, row in zip(chunk_ids, rows):
        conn.execute(
            "INSERT INTO chunks_fts (id, document_id, text) VALUES (?, ?, ?)",
            (cid, document_id, row[3]),
        )

    conn.execute(
        "UPDATE documents SET chunk_count = ? WHERE id = ?",
        (len(chunks), document_id),
    )
    conn.commit()
    conn.close()
    return chunk_ids


def get_chunks(document_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def keyword_search_chunks(
    query: str, doc_ids: Optional[List[str]] = None, limit: int = 20
) -> List[Dict]:
    """FTS5 keyword search over chunks. Returns [] on any database error."""
    try:
        conn = get_connection()
        safe_q = query.replace('"', '""')
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            rows = conn.execute(
                f"""SELECT c.*, rank FROM chunks c
                    JOIN chunks_fts f ON c.id = f.id
                    WHERE chunks_fts MATCH ?
                      AND c.document_id IN ({placeholders})
                    ORDER BY rank LIMIT ?""",
                [f'"{safe_q}"'] + doc_ids + [limit],
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.*, rank FROM chunks c
                   JOIN chunks_fts f ON c.id = f.id
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (f'"{safe_q}"', limit),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.DatabaseError:
        return []


# ─── Templates ────────────────────────────────────────────────────────────────

def add_template(
    name: str,
    description: str,
    fields: List[Dict],
    created_by: str = "admin",
) -> str:
    tid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO templates (id, name, description, fields, created_date, updated_date, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (tid, name, description, json.dumps(fields), now, now, created_by),
    )
    conn.commit()
    conn.close()
    return tid


def get_template(template_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    if not row:
        return None
    t = dict(row)
    t["fields"] = json.loads(t["fields"])
    return t


def list_templates() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM templates ORDER BY created_date DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        t = dict(r)
        t["fields"] = json.loads(t["fields"])
        result.append(t)
    return result


def update_template(template_id: str, name: str, description: str, fields: List[Dict]) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE templates SET name=?, description=?, fields=?, updated_date=?
           WHERE id=?""",
        (name, description, json.dumps(fields), datetime.utcnow().isoformat(), template_id),
    )
    conn.commit()
    conn.close()


def delete_template(template_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    conn.close()


# ─── Template Results ─────────────────────────────────────────────────────────

def save_template_result(
    template_id: str,
    document_ids: List[str],
    results: Dict,
) -> str:
    rid = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        """INSERT INTO template_results (id, template_id, document_ids, results, generated_date)
           VALUES (?, ?, ?, ?, ?)""",
        (rid, template_id, json.dumps(document_ids), json.dumps(results), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return rid


def get_template_results(template_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM template_results WHERE template_id = ? ORDER BY generated_date DESC",
        (template_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        t = dict(r)
        t["document_ids"] = json.loads(t["document_ids"] or "[]")
        t["results"] = json.loads(t["results"] or "{}")
        result.append(t)
    return result


def approve_template_result(result_id: str, notes: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE template_results SET approved=1, notes=? WHERE id=?",
        (notes, result_id),
    )
    conn.commit()
    conn.close()


# ─── Entities ─────────────────────────────────────────────────────────────────

def add_entities(document_id: str, entities: List[Dict]) -> None:
    conn = get_connection()
    rows = [
        (
            str(uuid.uuid4()),
            document_id,
            e.get("chunk_id"),
            e.get("type", "MISC"),
            e.get("text", ""),
            e.get("confidence", 1.0),
        )
        for e in entities
    ]
    conn.executemany(
        "INSERT INTO entities (id, document_id, chunk_id, entity_type, entity_text, confidence) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def get_entities(document_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM entities WHERE document_id = ? ORDER BY entity_type",
        (document_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_entities() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM entities ORDER BY entity_type").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Stats ────────────────────────────────────────────────────────────────────

# ─── Checklists ───────────────────────────────────────────────────────────────

def add_checklist(name: str, description: str, template_ids: List[str]) -> str:
    cid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO checklists (id, name, description, template_ids, created_date, updated_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (cid, name, description, json.dumps(template_ids), now, now),
    )
    conn.commit()
    conn.close()
    return cid


def get_checklist(checklist_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM checklists WHERE id = ?", (checklist_id,)).fetchone()
    conn.close()
    if not row:
        return None
    c = dict(row)
    c["template_ids"] = json.loads(c["template_ids"])
    return c


def list_checklists() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM checklists ORDER BY created_date DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        c = dict(r)
        c["template_ids"] = json.loads(c["template_ids"])
        result.append(c)
    return result


def update_checklist(checklist_id: str, name: str, description: str, template_ids: List[str]) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE checklists SET name=?, description=?, template_ids=?, updated_date=?
           WHERE id=?""",
        (name, description, json.dumps(template_ids), datetime.utcnow().isoformat(), checklist_id),
    )
    conn.commit()
    conn.close()


def delete_checklist(checklist_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM checklists WHERE id = ?", (checklist_id,))
    conn.commit()
    conn.close()


# ─── Inspections ──────────────────────────────────────────────────────────────

def add_inspection(
    name: str,
    checklist_id: str,
    checklist_name: str,
    inspection_date: str,
    results: Dict,
) -> str:
    iid = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        """INSERT INTO inspections
           (id, name, checklist_id, checklist_name, inspection_date, results, created_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (iid, name, checklist_id, checklist_name, inspection_date, json.dumps(results), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return iid


def get_inspection(inspection_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    r["results"] = json.loads(r["results"])
    return r


def list_inspections(checklist_id: Optional[str] = None) -> List[Dict]:
    conn = get_connection()
    if checklist_id:
        rows = conn.execute(
            "SELECT * FROM inspections WHERE checklist_id = ? ORDER BY inspection_date DESC",
            (checklist_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM inspections ORDER BY inspection_date DESC"
        ).fetchall()
    conn.close()
    result = []
    for r in rows:
        rec = dict(r)
        rec["results"] = json.loads(rec["results"])
        result.append(rec)
    return result


# ─── Stats ────────────────────────────────────────────────────────────────────

def clear_all_data() -> None:
    """
    Wipe all data by deleting the SQLite file and recreating the schema.
    This is safer than DELETE statements because FTS5 content tables can
    become corrupted when the backing table is cleared independently.
    """
    try:
        DB_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    init_db()


def get_stats() -> Dict[str, int]:
    conn = get_connection()
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    templates = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    processed = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE status='processed'"
    ).fetchone()[0]
    conn.close()
    return {
        "documents": docs,
        "chunks": chunks,
        "templates": templates,
        "entities": entities,
        "processed": processed,
    }
