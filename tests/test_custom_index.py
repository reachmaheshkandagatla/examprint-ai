from io import BytesIO

import pymupdf as fitz
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.custom_index import extract_custom_topics
from src.index_engine import make_entries


@pytest.fixture
def marked_pdf(tmp_path):
    path = tmp_path / "marked.pdf"
    with fitz.open() as doc:
        for lines in [
            ["Topic: Neural Networks", "Subtopic: Ignore this", "Topic:", "Unrelated body text"],
            ["topic: neural networks", "Topic: Optimization", "Topic: Optimization", "Unit [1]: Literal marker"],
            ["Topic: Probability"],
            [],
        ]:
            page = doc.new_page()
            for index, line in enumerate(lines):
                page.insert_text((40, 50 + index * 35), line, fontsize=16)
        doc.save(path)
    return path


def test_literal_markers_duplicates_and_mapping(marked_pdf):
    result = extract_custom_topics(marked_pdf, "Topic:")
    assert result["custom_topics"] == [
        {"topic": "Neural Networks", "source_pages": [0, 1]},
        {"topic": "Optimization", "source_pages": [1]},
        {"topic": "Probability", "source_pages": [2]},
    ]
    assert result["empty_matches"] == 1
    assert result["unavailable_pages"] == [3]
    assert [e["printed_page_reference"] for e in make_entries(result["custom_topics"], 1)] == ["1–2", "2", "3"]
    assert [e["printed_page_reference"] for e in make_entries(result["custom_topics"], 2)] == ["1", "1", "2"]
    assert extract_custom_topics(marked_pdf, "Unit [1]:")["custom_topics"] == [
        {"topic": "Literal marker", "source_pages": [1]}]
    assert not extract_custom_topics(marked_pdf, ".*")["custom_topics"]
    with pytest.raises(ValueError, match="Enter a custom marker"):
        extract_custom_topics(marked_pdf, "  ")


def test_marker_split_into_pdf_spans(tmp_path):
    path = tmp_path / "spans.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 50), "Topic:", fontsize=16)
        page.insert_text((100, 50), "Separate spans", fontsize=16)
        doc.save(path)
    assert extract_custom_topics(path, "Topic:")["custom_topics"] == [
        {"topic": "Separate spans", "source_pages": [0]}]


def test_custom_source_ui_preserves_edits_and_clears_stale_matches(marked_pdf, tmp_path, monkeypatch):
    uploaded = BytesIO(marked_pdf.read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "marked.pdf", "custom-upload", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "custom.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    def button(label):
        return next(b for b in app.button if b.label == label)
    next(s for s in app.selectbox if s.label == "Slides per side").set_value(1).run()
    before = app.session_state.entries
    next(s for s in app.selectbox if s.label == "Index source").set_value("Custom").run()
    assert not app.exception
    assert app.session_state.entries == before
    assert len(app.session_state.suggestions) == 3
    button("Use suggested index").click().run()
    assert [e["topic"] for e in app.session_state.entries] == ["Neural Networks", "Optimization", "Probability"]
    button("Generate selected index PDF").click().run()
    assert not app.exception and not app.error
    assert not next(d for d in app.get("download_button") if d.label == "Download selected index PDF").disabled
    next(t for t in app.text_input if t.label == "Custom topic marker").set_value("Unit [1]:").run()
    assert app.session_state.suggestions[0]["topic"] == "Literal marker"
    assert len(app.session_state.entries) == 3
    next(t for t in app.text_input if t.label == "Custom topic marker").set_value("No match:").run()
    assert app.session_state.suggestions == []
    assert not any(b.label == "Use suggested index" for b in app.button)
    next(t for t in app.text_input if t.label == "Custom topic marker").set_value(" ").run()
    assert button("Extract / refresh suggested topics").disabled
    assert app.session_state.suggestions == []
    assert len(app.session_state.entries) == 3
    next(s for s in app.selectbox if s.label == "Index source").set_value("Slide headings").run()
    assert not app.exception and app.session_state.suggestions
