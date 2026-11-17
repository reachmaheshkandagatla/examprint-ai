"""ExamPrint AI: all document processing stays on this computer."""
from dataclasses import asdict
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import os
import pymupdf as fitz
import pandas as pd
import streamlit as st
from src.database import Database
from src.editor_state import apply_editor_changes
from src.export_engine import export_print, export_csv, export_zip
from src.index_engine import (make_entries, remap_entries, validate_entries, parse_reference,
                              merge_entries, export_index, index_sort_key, index_issues, INDEX_FORMAT_VERSION)
from src.layout_engine import LayoutSettings, page_counts, readability_warning
from src.pdf_engine import PDFError, validate_pdf, safe_filename, open_pdf
from src.preview_engine import generate_preview, render_preview_page
from src.topic_extractor import extract_headings, suggested_topics, EXTRACTOR_VERSION

st.set_page_config(page_title="ExamPrint AI", page_icon="📄", layout="wide")
st.title("ExamPrint AI")
st.caption("Offline lecture handouts · Separate, editable topic index · Duplex-ready A4")
st.html("""
<style>
[data-testid="stDownloadButton"] button:not(:disabled) {
    background-color: #2563eb;
    border-color: #2563eb;
    color: white;
}
[data-testid="stDownloadButton"] button:not(:disabled):hover {
    background-color: #1d4ed8;
    border-color: #1d4ed8;
    color: white;
}
</style>
""")


def switch_tab(label):
    st.session_state.workflow_tab = label


def next_tab(label, disabled=False):
    st.divider()
    st.button(f"Next: {label} →", key=f"next_{label}",
              on_click=switch_tab, args=(label,), disabled=disabled)


def revise(entries):
    st.session_state.entries = entries
    st.session_state.revision = st.session_state.get("revision", 0) + 1


def edit_rows(key):
    model = st.session_state.editor_model
    st.session_state.entries = apply_editor_changes(
        model["baseline"], model["visible"], st.session_state[key], model["added_ids"])


def download(label, path, mime, key):
    with open(path, "rb") as stream:
        st.download_button(label, stream, file_name=Path(path).name, mime=mime, key=key)


def index_signature(meta, settings, entries):
    return sha256(json.dumps([INDEX_FORMAT_VERSION, meta["file_hash"], asdict(settings), entries], sort_keys=True).encode()).hexdigest()


def generate_index_files(entries, work, total_sides, signature):
    export_index(entries, work / "ExamIndex.pdf", total_sides)
    export_csv(entries, work / "ExamIndex.csv")
    st.session_state.export_signature = signature
    st.session_state.zip_signature = None


def move_preview(delta, total, per_side):
    current = (int(st.session_state.start_slide) - 1) // per_side
    side = max(0, min((total - 1) // per_side, current + delta))
    st.session_state.start_slide = side * per_side + 1


if "workspace" not in st.session_state:
    st.session_state.workspace = TemporaryDirectory(prefix="examprint-")
work = Path(st.session_state.workspace.name)
db = Database(os.environ.get("EXAMPRINT_DB", "data/examprint.sqlite3"))
tabs = st.tabs(["Upload & Configure", "Print Preview", "Editable Topic Index", "Export"],
               key="workflow_tab", on_change="rerun")

with tabs[0]:
    uploaded = st.file_uploader("Lecture PDF", type=["pdf"], key=f'upload_{st.session_state.get("upload_epoch", 0)}')
    password = st.text_input("PDF password (if required)", type="password")
    if uploaded is None:
        st.info("Upload a PDF to configure your handout.")
        next_tab("Print Preview", disabled=True)
        st.stop()
    limit = int(os.environ.get("EXAMPRINT_MAX_UPLOAD_MB", "250"))
    if uploaded.size > limit * 1024 * 1024:
        st.error(f"Maximum upload size is {limit} MB.")
        st.stop()
    upload_token = (uploaded.file_id, sha256(password.encode()).hexdigest())
    if st.session_state.get("upload_token") != upload_token:
        source = work / "input.pdf"
        # Release previous generated files before accepting another document.
        for path in work.iterdir():
            if path.is_file():
                path.unlink()
        source.write_bytes(uploaded.getbuffer())
        try:
            meta = validate_pdf(source, limit * 1024 * 1024, password)
        except (PDFError, OSError, ValueError) as exc:
            st.error(str(exc))
            st.stop()
        document_id = db.register(safe_filename(uploaded.name), meta["file_hash"], meta["total_pages"])
        saved_layout, entries = db.restore(document_id)
        layout = saved_layout or LayoutSettings()
        for name, value in asdict(layout).items():
            st.session_state[name] = value
        st.session_state.pop("editor_model", None)
        st.session_state.update(upload_token=upload_token, meta=meta, document_id=document_id,
                                entries=entries, revision=0, layout=layout, start_slide=1,
                                preview_signature=None, export_signature=None, extraction=None, suggestions=[],
                                has_saved_index=saved_layout is not None)
    source = work / "input.pdf"
    meta = st.session_state.meta
    document_id = st.session_state.document_id
    col1, col2, col3 = st.columns(3)
    col1.metric("Original pages", meta["total_pages"])
    col2.metric("File size", f'{meta["size"] / 1024 / 1024:.1f} MB')
    col3.caption(safe_filename(uploaded.name))
    cols = st.columns(3)
    cols[0].selectbox("Paper", ["A4"], key="paper_size")
    cols[1].selectbox("Slides per side", [2, 3, 4, 6], key="slides_per_side")
    cols[2].selectbox("Orientation", ["Portrait", "Landscape"], key="orientation")
    cols = st.columns(2)
    cols[0].number_input("Margins (mm)", min_value=0.0, max_value=40.0, step=1.0, key="margin")
    cols[1].number_input("Slide spacing (mm)", min_value=0.0, max_value=30.0, step=1.0, key="spacing")
    try:
        settings = LayoutSettings(**{name: st.session_state[name] for name in asdict(LayoutSettings())})
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    if settings != st.session_state.layout:
        revise(remap_entries(st.session_state.entries, settings.slides_per_side))
        st.session_state.layout = settings
    total_sides, total_sheets = page_counts(meta["total_pages"], settings)
    col1, col2 = st.columns(2)
    col1.metric("Printed sides", total_sides)
    col2.metric("Physical sheets (duplex)", total_sheets)
    st.info("Print at actual size (100%), one PDF page per side, with duplex enabled. "
            + ("Use long-edge binding for portrait." if settings.orientation == "Portrait" else "Use short-edge binding for landscape.")
            + " Test one sheet first; printer settings vary. The index is printed separately.")
    with open_pdf(source, password) as document:
        warning = readability_warning(document[0].rect, settings)
    if warning:
        st.warning(warning)
    st.caption("Layout controls above also apply to preview and export. Visible annotations are flattened; embedded PDF actions are not copied.")
    next_tab("Print Preview")

with tabs[1]:
    st.subheader("Three-side print preview")
    st.number_input("Starting slide", min_value=1, max_value=meta["total_pages"], step=1, key="start_slide")
    cols = st.columns(3)
    cols[0].button("Previous", on_click=move_preview, args=(-1, meta["total_pages"], settings.slides_per_side))
    cols[1].button("Next", on_click=move_preview, args=(1, meta["total_pages"], settings.slides_per_side))
    zoom = cols[2].slider("Zoom", min_value=.5, max_value=2.0, value=1.0, step=.25)
    first_side = (st.session_state.start_slide - 1) // settings.slides_per_side
    preview_sig = (meta["file_hash"], settings, first_side)
    if st.button("Generate / refresh preview", type="primary"):
        try:
            generate_preview(source, work / "Preview.pdf", settings, st.session_state.start_slide, password)
            st.session_state.preview_signature = preview_sig
        except (PDFError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
    if st.session_state.preview_signature == preview_sig and (work / "Preview.pdf").exists():
        download("Download preview PDF", work / "Preview.pdf", "application/pdf", "preview_download")
        columns = st.columns(min(3, total_sides - first_side))
        for offset, column in enumerate(columns):
            side = first_side + offset
            column.caption(f"Printed page {side + 1} · Sheet {side // 2 + 1} · {'Front' if side % 2 == 0 else 'Back'}")
            column.image(render_preview_page(work / "Preview.pdf", offset, zoom))
    else:
        st.caption("Generate the preview for the current settings and starting slide. Only the selected three sides are processed.")
    next_tab("Editable Topic Index")

with tabs[2]:
    st.caption("Topics use PDF bookmarks, native text, font sizes, and heading-position heuristics. No semantic AI or OCR is used.")
    index_source = st.selectbox("Index source", ["Auto", "Table of contents", "Sessions & course plans", "Course plans", "Slide headings"])
    st.caption("Auto uses sessions when present, then a table of contents, then course plans or slide headings. Subtopics are matched within their session; next-session notices are ignored. Unmatched topics stay excluded for manual assignment.")
    density = st.selectbox("Index density (slide headings)", ["Compact", "Balanced", "Detailed"], index=1)
    refresh_topics = st.button("Extract / refresh suggested topics")
    if refresh_topics or st.session_state.extraction is None or st.session_state.get("extraction_version") != EXTRACTOR_VERSION:
        progress = st.progress(0.0, text="Reading native PDF text…")
        try:
            extraction = db.cached_extraction(document_id, EXTRACTOR_VERSION)
            if extraction is None:
                extraction = extract_headings(source, password, progress.progress)
                db.cache_extraction(document_id, EXTRACTOR_VERSION, extraction)
            st.session_state.extraction = extraction
            st.session_state.extraction_version = EXTRACTOR_VERSION
            proposed = make_entries(suggested_topics(extraction, index_source, density), settings.slides_per_side)
            # Preserve all saved edits and deletions; density changes are explicit suggestions.
            st.session_state.suggestions = proposed
            if not st.session_state.entries and not st.session_state.has_saved_index:
                revise(proposed)
                st.session_state.has_saved_index = True
        except (PDFError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
        finally:
            progress.empty()
    extraction = st.session_state.extraction
    if extraction and extraction["unavailable_pages"]:
        st.warning(f'Native text extraction unavailable on {len(extraction["unavailable_pages"])} pages. Add their topics manually; OCR is not included.')
    if extraction:
        st.session_state.suggestions = make_entries(suggested_topics(extraction, index_source, density), settings.slides_per_side)
        toc = extraction.get("toc", {})
        if index_source == "Table of contents" or (index_source == "Auto" and toc.get("topics") and not extraction.get("sessions")):
            st.caption(f"Found {len(toc.get('topics', []))} contents entries using {toc.get('method', 'contents pages')}. Main headings and indented subtopics share a group. Deeper levels are grouped beneath the main heading.")
            st.info("Choose Use suggested index below to apply these suggestions. Existing edits are preserved until you replace them. Inferred page references need review.")
            if not toc.get("topics"):
                st.warning("No readable table of contents or PDF bookmarks found. Scanned contents need OCR, which is not supported; add entries manually or choose another index source.")
        plans = extraction.get("course_plans", [])
        if index_source != "Slide headings":
            st.caption(f"Found {len(plans)} course-plan slides and {len(extraction.get('course_topics', []))} unique plan topics.")
        if extraction.get("sessions") and index_source in ("Auto", "Sessions & course plans"):
            st.caption(f"Found {len(extraction['sessions'])} session headings. Grouped sessions share one start page; subtopics are grouped beneath them.")
            if extraction.get("missing_sessions"):
                st.warning("No explicit heading found for session(s): " + ", ".join(map(str, extraction["missing_sessions"])) + ". Review unassigned topics; no session page is invented.")
        unresolved = sum(not e["source_pages"] for e in st.session_state.suggestions)
        if unresolved:
            st.warning(f"{unresolved} topics could not be matched to lecture headings. Assign their printed pages, include them, and confirm review before exporting.")
        if st.session_state.suggestions:
            st.caption("Use suggested index replaces the current index. Saved changes remain available through Restore until you save again.")
            if st.button("Use suggested index"):
                revise(st.session_state.suggestions)
                st.rerun()
            if st.button("Add missing suggestions (preserve current edits)"):
                known = {(e.get("section", ""), e["topic"].casefold()) for e in st.session_state.entries}
                revise(st.session_state.entries + [e for e in st.session_state.suggestions if (e.get("section", ""), e["topic"].casefold()) not in known])
    query = st.text_input("Search topics")
    sort_alpha = st.checkbox("Sort topics alphabetically within groups", value=True)
    entries = st.session_state.entries
    visible = [e for e in entries if query.casefold() in (e.get("section", "") + " " + e["topic"]).casefold()]
    if sort_alpha:
        visible.sort(key=index_sort_key)
    editor_context = (document_id, st.session_state.revision, query, sort_alpha)
    model = st.session_state.get("editor_model")
    if model is None or model["context"] != editor_context:
        model = {"context": editor_context, "key": f"editor_{uuid4().hex}",
                 "baseline": deepcopy(entries), "visible": deepcopy(visible), "added_ids": {}}
        st.session_state.editor_model = model
    # Keep both the widget identity and its input data unchanged during cell edits.
    # Streamlit applies cumulative deltas to this snapshot and retains grid scroll/focus.
    rows = [{"Session": e.get("section", ""), "Type": e.get("kind", "topic"), "Topic": e["topic"], "Printed Page": e["printed_page_reference"],
             "Included": e["included"], "Needs Review": e.get("needs_review", False)} for e in model["visible"]]
    editor_key = model["key"]
    st.data_editor(pd.DataFrame(rows, columns=["Included", "Printed Page", "Topic", "Session", "Type", "Needs Review"]),
                   key=editor_key, num_rows="dynamic", hide_index=True, disabled=["Needs Review"],
                   column_config={"Session": st.column_config.TextColumn("Group / Heading"),
                                  "Type": st.column_config.SelectboxColumn(options=["session", "topic", "heading", "subtopic"], default="topic", required=True),
                                  "Topic": st.column_config.TextColumn(required=True),
                                  "Printed Page": st.column_config.TextColumn(required=True, width="small"),
                                  "Included": st.column_config.CheckboxColumn(default=True)},
                   on_change=edit_rows, args=(editor_key,), height=520, use_container_width=True)
    st.caption("Edits apply immediately without reordering rows. Change the search or sort setting to refresh the view. Save changes to retain them across sessions. Page references accept values such as 2, 5–8.")
    issues = index_issues(entries, total_sides)
    invalid_ids = {issue["id"] for issue in issues}
    if issues:
        st.error(f"{len(issues)} selected entries have missing or invalid page references or details. Confirming review cannot supply missing page numbers.")
        st.dataframe(pd.DataFrame([{k: v for k, v in issue.items() if k != "id"} for issue in issues]),
                     hide_index=True, use_container_width=True)
        if st.button("Exclude invalid entries and generate PDF"):
            revise([{**e, "included": False} if e["id"] in invalid_ids else e for e in entries])
            st.session_state.generate_valid_index = True
            st.rerun()
    if any(e["included"] and e.get("needs_review") for e in entries):
        st.warning("Selected references or group assignments need review. Confirmation applies to entries with valid page references; invalid rows remain listed above.")
        if st.button("Confirm reviewed page references"):
            revise([{**e, "needs_review": False} if e["included"] and e["id"] not in invalid_ids else e for e in entries])
            st.rerun()
    st.subheader("Download selected index")
    selected_count = sum(e["included"] for e in st.session_state.entries)
    st.caption(f"{selected_count} entries selected via Included. The PDF includes all selected entries, even when search hides some rows. Saving or generating the lecture PDF is not required.")
    current_index_sig = index_signature(meta, settings, st.session_state.entries)
    generate_clicked = st.button("Generate selected index PDF", type="primary", disabled=selected_count == 0)
    generate_clicked = st.session_state.pop("generate_valid_index", False) or generate_clicked
    refresh_needed = bool(st.session_state.export_signature) and (
        st.session_state.export_signature != current_index_sig or not (work / "ExamIndex.pdf").exists())
    if selected_count and (generate_clicked or refresh_needed):
        try:
            generate_index_files(st.session_state.entries, work, total_sides, current_index_sig)
            if generate_clicked:
                st.success("Your selected index is ready. Download ExamIndex.pdf below.")
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
            st.info("Correct the selected rows, confirm reviewed references above, or uncheck Included for entries you want to leave out.")
    if selected_count == 0:
        st.info("Check Included for at least one entry to generate an index PDF.")
    index_ready = (selected_count > 0 and st.session_state.export_signature == current_index_sig
                   and (work / "ExamIndex.pdf").exists())
    if index_ready:
        download("Download selected index PDF", work / "ExamIndex.pdf", "application/pdf", "selected_index_download")
        st.caption("After the first generation, valid edits automatically refresh this PDF. You can download it again anytime.")
    else:
        st.download_button("Download selected index PDF", data=b"", file_name="ExamIndex.pdf",
                           mime="application/pdf", key="selected_index_download", disabled=True)
    cols = st.columns(2)
    if cols[0].button("Save changes", type="primary"):
        try:
            validate_entries(st.session_state.entries, total_sides, require_review=False)
            db.save(document_id, settings, st.session_state.entries)
            st.success("Index and layout saved locally.")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    if cols[1].button("Restore saved changes"):
        saved_layout, restored = db.restore(document_id)
        if saved_layout:
            revise(remap_entries(restored, settings.slides_per_side) if saved_layout != settings else restored)
            st.rerun()
        else:
            st.info("No saved index for this document.")
    with st.expander("Merge topics"):
        labels = {e["id"]: (e.get("section", "") + " / " if e.get("section") else "") + e["topic"] for e in entries}
        selected = st.multiselect("Topics to merge", list(labels), format_func=labels.get,
                                  key=f"merge_topics_{document_id}_{st.session_state.revision}")
        name = st.text_input("Merged topic name")
        if st.button("Merge selected topics"):
            try:
                revise(merge_entries(entries, selected, name, total_sides))
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    if entries:
        labels = {e["id"]: (e.get("section", "") + " / " if e.get("section") else "") + e["topic"] for e in entries}
        selected_id = st.selectbox("Preview topic", list(labels), format_func=labels.get,
                                   key=f"preview_topic_{document_id}_{st.session_state.revision}")
        if st.button("Preview selected topic's printed page"):
            try:
                selected_entry = next(e for e in entries if e["id"] == selected_id)
                page_number = parse_reference(selected_entry["printed_page_reference"], total_sides)[0]
                generate_preview(source, work / "TopicPreview.pdf", settings, (page_number - 1) * settings.slides_per_side + 1, password)
                st.caption(f"Printed page {page_number}")
                st.image(render_preview_page(work / "TopicPreview.pdf"))
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    next_tab("Export")

with tabs[3]:
    st.caption("ExamPrint.pdf and ExamIndex.pdf remain separate. Cross-file index links depend on the PDF viewer; keep both files in the same folder.")
    export_sig = index_signature(meta, settings, st.session_state.entries)
    if st.button("Generate ExamPrint.pdf", type="primary"):
        progress = st.progress(0.0, text="Generating printed sides…")
        try:
            export_print(source, work / "ExamPrint.pdf", settings, password, progress.progress)
            st.session_state.print_signature = (meta["file_hash"], settings)
            st.success("Print PDF ready.")
        except (PDFError, ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
        finally:
            progress.empty()
    print_ready = st.session_state.get("print_signature") == (meta["file_hash"], settings) and (work / "ExamPrint.pdf").exists()
    if print_ready:
        download("Download ExamPrint.pdf", work / "ExamPrint.pdf", "application/pdf", "print_download")
    if st.button("Generate index, CSV, and ZIP"):
        try:
            generate_index_files(st.session_state.entries, work, total_sides, export_sig)
            if print_ready:
                export_zip(work / "ExamPrint.pdf", work / "ExamIndex.pdf", work / "ExamPrint.zip")
            st.session_state.export_signature = export_sig
            st.session_state.zip_signature = export_sig if print_ready else None
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    export_index_ready = (selected_count > 0 and st.session_state.export_signature == export_sig
                          and (work / "ExamIndex.pdf").exists())
    if export_index_ready:
        download("Download ExamIndex.pdf", work / "ExamIndex.pdf", "application/pdf", "index_download")
    else:
        st.download_button("Download ExamIndex.pdf", data=b"", file_name="ExamIndex.pdf",
                           mime="application/pdf", key="index_download", disabled=True)
        st.caption("Generate the index here or in Editable Topic Index to enable its PDF download.")
    if export_index_ready:
        download("Download editable index CSV", work / "ExamIndex.csv", "text/csv", "csv_download")
        if print_ready:
            # Rebuild if the print PDF was generated after the index.
            if st.session_state.get("zip_signature") != export_sig:
                export_zip(work / "ExamPrint.pdf", work / "ExamIndex.pdf", work / "ExamPrint.zip")
                st.session_state.zip_signature = export_sig
            download("Download both PDFs in ZIP", work / "ExamPrint.zip", "application/zip", "zip_download")
    if st.button("Clear session and temporary PDFs"):
        next_epoch = st.session_state.get("upload_epoch", 0) + 1
        st.session_state.workspace.cleanup()
        st.session_state.clear()
        st.session_state.upload_epoch = next_epoch
        st.rerun()
