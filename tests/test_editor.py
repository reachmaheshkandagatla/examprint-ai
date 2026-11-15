from copy import deepcopy
from src.editor_state import apply_editor_changes
from src.index_engine import make_entries


def test_cumulative_edits_additions_and_deletions():
    baseline = make_entries([{"topic": f"Topic {i}", "source_pages": [i]} for i in range(4)], 3)
    snapshot = deepcopy(baseline)
    visible = [baseline[1], baseline[3]]
    added_ids = {}
    changes = {"edited_rows": {0: {"Topic": "Renamed", "Printed Page": "2"}},
               "deleted_rows": [1], "added_rows": [{"Topic": "New topic", "Printed Page": "1"}]}
    first = apply_editor_changes(baseline, visible, changes, added_ids)
    second = apply_editor_changes(baseline, visible, changes, added_ids)
    assert first == second  # No duplicate additions or repeated deletions.
    assert baseline == snapshot
    assert len(first) == 4
    assert [e["topic"] for e in first] == ["Topic 0", "Renamed", "Topic 2", "New topic"]
    assert first[1]["manually_edited"]
    # Reverting a cumulative edit restores the original, rather than retaining a stale value.
    changes["edited_rows"] = {0: {"Included": False}}
    third = apply_editor_changes(baseline, visible, changes, added_ids)
    assert third[1]["topic"] == "Topic 1" and third[1]["printed_page_reference"] == "1"
    assert not third[1]["included"]
    assert third[-1]["id"] == first[-1]["id"]


def test_editor_widget_identity_survives_edits(pdf_factory, tmp_path, monkeypatch):
    from io import BytesIO
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    uploaded = BytesIO(pdf_factory(40).read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "slides.pdf", "editor-upload", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    model = app.session_state.editor_model
    key, original_rows = model["key"], deepcopy(model["visible"])
    for title in ("ZZZ new title", "AAA new title"):
        app.session_state.entries = apply_editor_changes(model["baseline"], model["visible"],
            {"edited_rows": {20: {"Topic": title}}, "deleted_rows": [], "added_rows": []}, model["added_ids"])
        app.run()
        assert not app.exception
        assert app.session_state.editor_model["key"] == key
        assert app.session_state.editor_model["visible"] == original_rows
        assert any(e["topic"] == title for e in app.session_state.entries)
    next(t for t in app.text_input if t.label == "Search topics").set_value("AAA").run()
    assert app.session_state.editor_model["key"] != key
    assert [e["topic"] for e in app.session_state.editor_model["visible"]] == ["AAA new title"]
