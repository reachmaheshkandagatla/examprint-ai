from io import BytesIO
from streamlit.testing.v1 import AppTest
import streamlit as st


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_initial_screen(tmp_path, monkeypatch):
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run()
    assert not app.exception
    assert app.title[0].value == "ExamPrint AI"
    assert len(app.tabs) == 4


def test_upload_preview_export_save(pdf_factory, tmp_path, monkeypatch):
    uploaded = BytesIO(pdf_factory(10).read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "lecture.pdf", "test-upload", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    assert not app.exception
    assert len(app.session_state.entries) == 10
    for label in ["Print Preview", "Editable Topic Index", "Export"]:
        button(app, f"Next: {label} →").click().run()
        assert not app.exception
        assert app.session_state.workflow_tab == label
    document_id = app.session_state.document_id
    entry_ids = [entry["id"] for entry in app.session_state.entries]
    button(app, "Home — Upload & Configure").click().run()
    assert not app.exception
    assert app.session_state.workflow_tab == "Upload & Configure"
    assert app.session_state.document_id == document_id
    assert [entry["id"] for entry in app.session_state.entries] == entry_ids
    assert next(d for d in app.get("download_button") if d.label == "Download ExamIndex.pdf").disabled
    button(app, "Generate / refresh preview").click().run()
    assert not app.exception
    assert app.session_state.preview_signature is not None
    button(app, "Next").click().run()
    assert app.session_state.start_slide == 4
    button(app, "Save changes").click().run()
    assert not app.exception
    button(app, "Generate ExamPrint.pdf").click().run()
    assert not app.exception
    button(app, "Generate index, CSV, and ZIP").click().run(timeout=20)
    assert not app.exception
    assert app.session_state.export_signature is not None
    assert not next(d for d in app.get("download_button") if d.label == "Download ExamIndex.pdf").disabled
    next(s for s in app.selectbox if s.label == "Slides per side").set_value(6).run()
    assert not app.exception
    assert app.session_state.entries[6]["printed_page_reference"] == "2"
    button(app, "Restore saved changes").click().run()
    assert not app.exception


def test_bad_upload(tmp_path, monkeypatch):
    uploaded = BytesIO(b"not pdf")
    uploaded.name, uploaded.file_id, uploaded.size = "bad.pdf", "bad-upload", 7
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run()
    assert not app.exception
    assert app.error


def test_selected_index_download_without_print_export(pdf_factory, tmp_path, monkeypatch):
    from pathlib import Path
    import pymupdf as fitz
    uploaded = BytesIO(pdf_factory(7).read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "lecture.pdf", "index-upload", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    entries = [dict(e, included=i == 0) for i, e in enumerate(app.session_state.entries)]
    # Excluded incomplete drafts must not prevent downloading the chosen entries.
    entries[-1].update(topic="", printed_page_reference="", needs_review=True)
    app.session_state.entries = entries
    app.run()
    button(app, "Generate selected index PDF").click().run()
    assert not app.exception and not app.error
    work = Path(app.session_state.workspace.name)
    assert not (work / "ExamPrint.pdf").exists()
    with fitz.open(work / "ExamIndex.pdf") as doc:
        text = "".join(page.get_text() for page in doc)
        assert "Topic 1" in text and "Topic 2" not in text
    assert any(d.label == "Download selected index PDF" for d in app.get("download_button"))
    assert not next(d for d in app.get("download_button") if d.label == "Download ExamIndex.pdf").disabled
    # Editing a selection refreshes the PDF and keeps the download available.
    app.session_state.entries[1]["included"] = True
    app.run()
    assert not next(d for d in app.get("download_button") if d.label == "Download selected index PDF").disabled
    with fitz.open(work / "ExamIndex.pdf") as doc:
        assert "Topic 2" in doc[0].get_text()
    # Further revisions and reruns keep serving the current PDF without Generate.
    for title, reference in [("Revised topic", "2"), ("Final topic", "3")]:
        app.session_state.entries[0].update(topic=title, printed_page_reference=reference, manually_edited=True)
        app.run()
        assert not app.exception and not app.error
        assert not next(d for d in app.get("download_button") if d.label == "Download selected index PDF").disabled
        with fitz.open(work / "ExamIndex.pdf") as doc:
            assert title in doc[0].get_text()
            assert any(link["page"] == int(reference) - 1 for link in doc[0].get_links())
        app.run()
        assert not next(d for d in app.get("download_button") if d.label == "Download selected index PDF").disabled
    app.session_state.entries[0]["needs_review"] = True
    app.run()
    button(app, "Generate selected index PDF").click().run()
    assert app.error and not app.exception
    assert next(d for d in app.get("download_button") if d.label == "Download selected index PDF").disabled
    button(app, "Confirm reviewed page references").click().run()
    button(app, "Generate selected index PDF").click().run()
    assert not app.exception and not app.error
    assert any(d.label == "Download selected index PDF" for d in app.get("download_button"))
    for entry in app.session_state.entries:
        entry["included"] = False
    app.run()
    assert button(app, "Generate selected index PDF").disabled


def test_review_with_missing_pages_then_download_valid_entries(pdf_factory, tmp_path, monkeypatch):
    from pathlib import Path
    import pymupdf as fitz
    uploaded = BytesIO(pdf_factory(7).read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "lecture.pdf", "missing-pages", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "ui.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    entries = app.session_state.entries
    entries[0].update(needs_review=True)
    entries[1].update(printed_page_reference="", included=True, needs_review=True)
    entries[2].update(printed_page_reference="999", included=True, needs_review=True)
    app.session_state.entries = entries
    app.run()
    assert any("2 selected entries" in error.value for error in app.error)
    button(app, "Confirm reviewed page references").click().run()
    assert not app.session_state.entries[0]["needs_review"]
    assert app.session_state.entries[1]["needs_review"]
    button(app, "Exclude invalid entries and generate PDF").click().run()
    assert not app.exception and not app.error
    assert not app.session_state.entries[1]["included"]
    assert not app.session_state.entries[2]["included"]
    assert not next(d for d in app.get("download_button") if d.label == "Download selected index PDF").disabled
    with fitz.open(Path(app.session_state.workspace.name) / "ExamIndex.pdf") as doc:
        text = doc[0].get_text()
        assert "Topic 1" in text and "Topic 2" not in text and "Topic 3" not in text


def test_one_slide_index_only_and_tab_status(pdf_factory, tmp_path, monkeypatch):
    from pathlib import Path
    import pymupdf as fitz
    uploaded = BytesIO(pdf_factory(7).read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = "lecture.pdf", "one-slide", len(uploaded.getbuffer())
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setenv("EXAMPRINT_DB", str(tmp_path / "one-slide.sqlite"))
    app = AppTest.from_file("../app.py").run(timeout=20)
    next(s for s in app.selectbox if s.label == "Slides per side").set_value(1).run()
    assert not app.exception
    assert [entry["printed_page_reference"] for entry in app.session_state.entries] == [str(i) for i in range(1, 8)]
    button(app, "Go straight to Editable Topic Index →").click().run()
    assert app.session_state.workflow_tab == "Editable Topic Index"
    button(app, "Generate selected index PDF").click().run()
    assert not app.exception and not app.error
    work = Path(app.session_state.workspace.name)
    assert not (work / "Preview.pdf").exists()
    assert not (work / "ExamPrint.pdf").exists()
    with fitz.open(work / "ExamIndex.pdf") as doc:
        assert [link["page"] for link in doc[0].get_links()] == list(range(7))
    status = app.session_state.processing_status
    assert "Complete · Generating the selected index PDF" in status
    button(app, "Next: Export →").click().run()
    assert app.session_state.processing_status == status
    button(app, "Save changes").click().run()
    button(app, "Restore saved changes").click().run()
    assert not app.exception and not app.error
    assert app.session_state.layout.slides_per_side == 1
