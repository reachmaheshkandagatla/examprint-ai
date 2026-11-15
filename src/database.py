"""Local metadata, saved index edits, and document-fingerprint extraction cache."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from .layout_engine import LayoutSettings


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY, filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL UNIQUE, total_pages INTEGER NOT NULL CHECK(total_pages > 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS layout_settings (
                    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                    slides_per_side INTEGER NOT NULL CHECK(slides_per_side IN (2,3,4,6)),
                    paper_size TEXT NOT NULL, orientation TEXT NOT NULL, margin REAL NOT NULL, spacing REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS index_entries (
                    id TEXT PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    topic TEXT NOT NULL, start_original_page INTEGER, end_original_page INTEGER,
                    printed_page_reference TEXT NOT NULL, manually_edited INTEGER NOT NULL CHECK(manually_edited IN (0,1)),
                    included INTEGER NOT NULL CHECK(included IN (0,1)), needs_review INTEGER NOT NULL DEFAULT 0,
                    source_pages TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS entries_document ON index_entries(document_id);
                CREATE TABLE IF NOT EXISTS extraction_cache (
                    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, payload TEXT NOT NULL);
            ''')
            columns = {row[1] for row in conn.execute("PRAGMA table_info(index_entries)")}
            for name, default in (("section", ""), ("kind", "topic")):
                if name not in columns:
                    conn.execute(f"ALTER TABLE index_entries ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def register(self, filename, file_hash, total_pages):
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO documents(filename,file_hash,total_pages) VALUES(?,?,?)",
                         (filename, file_hash, total_pages))
            return conn.execute("SELECT id FROM documents WHERE file_hash=?", (file_hash,)).fetchone()[0]

    def save(self, document_id, settings, entries):
        with self.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO layout_settings VALUES(?,?,?,?,?,?)",
                         (document_id, *asdict(settings).values()))
            conn.execute("DELETE FROM index_entries WHERE document_id=?", (document_id,))
            conn.executemany("INSERT INTO index_entries (id,document_id,topic,start_original_page,end_original_page,printed_page_reference,manually_edited,included,needs_review,source_pages,section,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", [
                (e["id"], document_id, e["topic"], e.get("start_original_page"), e.get("end_original_page"),
                 e["printed_page_reference"], int(e["manually_edited"]), int(e["included"]),
                 int(e.get("needs_review", False)), json.dumps(e["source_pages"]), e.get("section", ""), e.get("kind", "topic")) for e in entries])

    def restore(self, document_id):
        with self.connect() as conn:
            settings = conn.execute("SELECT * FROM layout_settings WHERE document_id=?", (document_id,)).fetchone()
            rows = conn.execute("SELECT * FROM index_entries WHERE document_id=? ORDER BY topic COLLATE NOCASE", (document_id,)).fetchall()
        entries = []
        for row in rows:
            entry = dict(row)
            entry.pop("document_id")
            entry["source_pages"] = json.loads(entry["source_pages"])
            for key in ("included", "manually_edited", "needs_review"):
                entry[key] = bool(entry[key])
            entries.append(entry)
        if settings:
            values = dict(settings)
            values.pop("document_id")
            return LayoutSettings(**values), entries
        return None, entries

    def cached_extraction(self, document_id, version):
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM extraction_cache WHERE document_id=? AND version=?", (document_id, version)).fetchone()
            return json.loads(row[0]) if row else None

    def cache_extraction(self, document_id, version, result):
        with self.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO extraction_cache VALUES(?,?,?)", (document_id, version, json.dumps(result)))
