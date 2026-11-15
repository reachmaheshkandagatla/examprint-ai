import csv
import sqlite3
import pymupdf as fitz
import pytest
from src.topic_extractor import extract_headings, suggested_topics
from src.session_index import session_on_page, text_lines
from src.index_engine import make_entries, remap_entries, export_index, index_sort_key, merge_entries
from src.database import Database
from src.layout_engine import LayoutSettings
from src.export_engine import export_csv


def session_pdf(path):
    with fitz.open() as doc:
        for index in range(18):
            page = doc.new_page(width=960, height=540)
            if index in (0, 6, 12):
                label, title = {0: ("Session 1", "Introduction to Machine Learning"),
                                6: ("Session 3&4", "Linear Models for Regression"),
                                12: ("Session 5 & 6", "Logistic Regression")}[index]
                page.insert_text((40, 60), label, fontsize=28)
                page.insert_text((40, 110), title, fontsize=28)
            elif index in (1, 7, 13):
                page.insert_text((40, 40), "Course Plan", fontsize=28)
                for row, title in enumerate(["Introduction", "Linear Models for Regression", "Linear Models for Classification"]):
                    y = 120 + 60 * row
                    page.insert_text((80, y), f"M{row + 1}", fontsize=20)
                    page.insert_text((220, y), title, fontsize=20)
                    if row == {1: 0, 7: 1, 13: 2}[index]:
                        page.draw_rect(fitz.Rect(60, y - 25, 800, y + 10), color=(1, 0, 0))
            elif index in (2, 8):
                page.insert_text((40, 40), "Agenda", fontsize=28)
                page.insert_text((60, 110), "o Shared Subtopic", fontsize=20)
                page.insert_text((60, 160), "o Missing Subtopic", fontsize=20)
            else:
                heading = {3: "Shared Subtopic", 9: "Shared Subtopic", 10: "Introduction",
                           11: "Next Session Plan : Module 4", 15: "Required reading for completed session"}.get(index, "Exercise")
                page.insert_text((40, 40), heading, fontsize=28)
                page.insert_text((40, 110), "Body text", fontsize=12)
        doc.save(path)


def test_session_hierarchy_and_local_references(tmp_path):
    path = tmp_path / "sessions.pdf"
    session_pdf(path)
    result = extract_headings(path)
    assert [s["label"] for s in result["sessions"]] == ["Session 1", "Session 3 & 4", "Session 5 & 6"]
    assert result["missing_sessions"] == [2]
    topics = suggested_topics(result)
    assert topics == suggested_topics(result, "Sessions & course plans")
    entries = make_entries(topics, 3)
    parents = [e for e in entries if e["kind"] == "session"]
    assert [e["printed_page_reference"] for e in parents] == ["1", "3", "5"]
    shared = [e for e in entries if e["topic"] == "Shared Subtopic"]
    assert [(e["section"], e["printed_page_reference"]) for e in shared] == [("Session 1", "2"), ("Session 3 & 4", "4")]
    intro = next(e for e in entries if e["topic"] == "Introduction")
    assert intro["section"] == "Session 1" and intro["printed_page_reference"] == "1"
    classification = next(e for e in entries if e["topic"] == "Linear Models for Classification")
    assert classification["section"] == "Session 5 & 6" and classification["printed_page_reference"] == "5"
    assert all(not e["included"] and e["needs_review"] for e in entries if e["topic"] == "Missing Subtopic")
    remapped = remap_entries(entries, 6)
    assert [e["printed_page_reference"] for e in remapped if e["kind"] == "session"] == ["1", "2", "3"]
    assert [e["section"] for e in remapped] == [e["section"] for e in entries]
    with pytest.raises(ValueError, match="one session"):
        merge_entries(entries, [e["id"] for e in shared], "Shared", 6)


@pytest.mark.parametrize("text,expected", [("Session 10 Topic: Support Vector Machine", [10]),
    ("Session 12 & 13", [12, 13]), ("Session 14: Unsupervised Learning", [14]),
    ("Session 3-4", [3, 4]), ("Next Session Plan : Module 5", None),
    ("Required Reading for completed session", None), ("As discussed in Session 2", None)])
def test_session_heading_variants(text, expected):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((20, 40), text, fontsize=18)
        found = session_on_page(text_lines(page.get_text("dict")["blocks"]), 0)
    assert (found["numbers"] if found else None) == expected


def test_hierarchy_persistence_and_exports(tmp_path):
    topics = [{"topic": "Session 10 — Later", "section": "Session 10", "kind": "session", "source_pages": [12]},
              {"topic": "A child", "section": "Session 2", "kind": "topic", "source_pages": [4]},
              {"topic": "Session 2 — Earlier", "section": "Session 2", "kind": "session", "source_pages": [3]}]
    entries = make_entries(topics, 3)
    db = Database(tmp_path / "db.sqlite")
    doc_id = db.register("test.pdf", "abc", 15)
    db.save(doc_id, LayoutSettings(), entries)
    loaded = db.restore(doc_id)[1]
    assert sorted(loaded, key=index_sort_key) == sorted(entries, key=index_sort_key)
    export_csv(loaded, tmp_path / "index.csv")
    with open(tmp_path / "index.csv", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["Session"] for row in rows] == ["Session 2", "Session 2", "Session 10"]
    assert [row["Type"] for row in rows] == ["session", "topic", "session"]
    output = export_index(loaded, tmp_path / "index.pdf", 5)
    with fitz.open(output) as doc:
        text = doc[0].get_text()
        assert text.index("Session 2") < text.index("A child") < text.index("Session 10")
        assert [link["page"] for link in doc[0].get_links()] == [1, 1, 4]


def test_existing_database_migration_preserves_edits(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE index_entries (id TEXT PRIMARY KEY, document_id INTEGER,
            topic TEXT, start_original_page INTEGER, end_original_page INTEGER,
            printed_page_reference TEXT, manually_edited INTEGER, included INTEGER,
            needs_review INTEGER, source_pages TEXT)''')
        conn.execute("INSERT INTO index_entries VALUES('old',1,'My edited topic',0,0,'3',1,1,0,'[0]')")
    db = Database(path)
    db.register("old.pdf", "abc", 9)
    _, entries = db.restore(1)
    assert entries[0]["topic"] == "My edited topic" and entries[0]["printed_page_reference"] == "3"
    assert entries[0]["section"] == "" and entries[0]["kind"] == "topic"
    Database(path)  # Repeat initialization must be safe.


def test_session_mode_ui(tmp_path, monkeypatch):
    from io import BytesIO
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    path = tmp_path / "sessions.pdf"
    session_pdf(path)
    uploaded = BytesIO(path.read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "sessions.pdf", "sessions", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    assert not app.exception
    assert len([e for e in app.session_state.entries if e.get("kind") == "session"]) == 3
    assert any("No explicit heading" in w.value for w in app.warning)
    next(b for b in app.button if b.label == "Save changes").click().run()
    assert not app.exception
    next(s for s in app.selectbox if s.label == "Slides per side").set_value(6).run()
    assert [e["printed_page_reference"] for e in app.session_state.entries if e.get("kind") == "session"] == ["1", "2", "3"]
    next(b for b in app.button if b.label == "Restore saved changes").click().run()
    assert not app.exception
    assert len([e for e in app.session_state.entries if e.get("kind") == "session"]) == 3
