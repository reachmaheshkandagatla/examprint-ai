import pymupdf as fitz

from src.database import Database
from src.index_engine import make_entries, remap_entries
from src.layout_engine import LayoutSettings
from src.topic_extractor import extract_headings, suggested_topics


def make_course_pdf(path):
    with fitz.open() as doc:
        for index in range(12):
            page = doc.new_page(width=960, height=540)
            if index in (0, 4, 8):
                page.insert_text((40, 45), "Course Plan", fontsize=28)
                names = ["Introduction", "Machine Learning Workflow"] if index != 8 else ["Decision Tree", "Unmatched Topic"]
                for row, name in enumerate(names):
                    page.insert_text((80, 130 + row * 50), f"M{row + 1}", fontsize=20)
                    page.insert_text((220, 130 + row * 50), name, fontsize=20)
                page.insert_text((30, 480), "Work Integrated Learning Programmes", fontsize=14)
            else:
                name = {1: "Introduction", 5: "Machine Learning Workflow", 9: "Decision Tree"}.get(index, f"Exercise {index}")
                page.insert_text((40, 45), name, fontsize=28)
                page.insert_text((40, 120), "Other lecture content", fontsize=12)
        doc.save(path)


def test_multiple_plans_deduplicate_and_map(tmp_path):
    path = tmp_path / "plans.pdf"
    make_course_pdf(path)
    extraction = extract_headings(path)
    assert len(extraction["course_plans"]) == 3
    topics = suggested_topics(extraction)
    assert [t["topic"] for t in topics] == ["Introduction", "Machine Learning Workflow", "Decision Tree", "Unmatched Topic"]
    assert [t["source_pages"] for t in topics] == [[1], [5], [9], []]
    entries = make_entries(topics, 3)
    assert [e["printed_page_reference"] for e in entries] == ["1", "2", "4", ""]
    assert not entries[-1]["included"] and entries[-1]["needs_review"]
    assert [e["printed_page_reference"] for e in remap_entries(entries, 6)] == ["1", "1", "2", ""]
    assert all(e["topic"] != "Exercise" for e in entries)
    assert any(t["topic"].startswith("Exercise") for t in suggested_topics(extraction, "Slide headings"))
    db = Database(tmp_path / "index.sqlite")
    doc_id = db.register("plans.pdf", "plans", 12)
    db.save(doc_id, LayoutSettings(), entries)
    restored = db.restore(doc_id)[1]
    assert next(e for e in restored if e["topic"] == "Unmatched Topic")["source_pages"] == []


def test_plan_occurrences_are_not_used_as_locations(tmp_path):
    path = tmp_path / "only-plan.pdf"
    with fitz.open() as doc:
        for _ in range(3):
            page = doc.new_page()
            page.insert_text((20, 40), "Course Plan", fontsize=28)
            page.insert_text((20, 110), "M1 Introduction", fontsize=20)
        doc.save(path)
    topics = suggested_topics(extract_headings(path))
    assert topics == [{"topic": "Introduction", "source_pages": []}]


def test_unlabelled_outline_and_heading_normalization(tmp_path):
    path = tmp_path / "outline.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((20, 40), "Course Outline", fontsize=28)
        page.insert_text((20, 110), "Instance-Based Learning", fontsize=20)
        page = doc.new_page()
        page.insert_text((20, 40), "Module 6: Instance Based Learning", fontsize=24)
        doc.save(path)
    assert suggested_topics(extract_headings(path)) == [{"topic": "Instance-Based Learning", "source_pages": [1]}]


def test_no_plan_falls_back_to_heading_mode(pdf_factory):
    extraction = extract_headings(pdf_factory(3))
    assert suggested_topics(extraction) == suggested_topics(extraction, "Slide headings")
    assert suggested_topics(extraction, "Course plans") == []


def test_course_plan_ui(tmp_path, monkeypatch):
    from io import BytesIO
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    path = tmp_path / "plans.pdf"
    make_course_pdf(path)
    uploaded = BytesIO(path.read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "plans.pdf", "course-upload", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    assert not app.exception
    assert len(app.session_state.entries) == 4
    original = app.session_state.entries
    next(s for s in app.selectbox if s.label == "Index source").set_value("Slide headings").run()
    assert app.session_state.entries == original
    next(b for b in app.button if b.label == "Use suggested index").click().run()
    assert any(e["topic"].startswith("Exercise") for e in app.session_state.entries)
    next(s for s in app.selectbox if s.label == "Index source").set_value("Course plans").run()
    next(b for b in app.button if b.label == "Use suggested index").click().run()
    assert len(app.session_state.entries) == 4
    next(b for b in app.button if b.label == "Save changes").click().run()
    assert not app.exception
