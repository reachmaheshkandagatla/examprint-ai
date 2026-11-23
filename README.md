# ExamPrint AI

Offline Streamlit application for A4 lecture handouts and a separate, editable topic index. Python 3.11+ required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the localhost address printed by Streamlit. Upload a PDF, configure the layout, generate a three-side preview, review the suggested topics, and export. Default output has three vertically stacked slides per side. Print `ExamPrint.pdf` at 100%, one PDF page per side, with printer duplex enabled. The app does not combine front and back onto a single PDF page.

To download only your selected index, check **Included** for the desired rows in **Editable Topic Index**, click **Generate selected index PDF**, then **Download selected index PDF** directly below the editor. Neither saving nor generating the lecture PDF is required. Search filters do not change which rows are included. Selected rows must have valid, reviewed page references; excluded rows do not block generation. Missing or invalid references appear in a separate table naming every affected topic. Confirming review acknowledges valid rows without inventing missing page numbers. Use **Exclude invalid entries and generate PDF** to retain those rows in the editor but leave them out of the downloaded index. The Included and Printed Page columns appear first for easy correction. After the first generation, valid changes to the index or layout automatically refresh the index PDF. The download stays visible; it is disabled with an explanation if selected references need correction or review.

Document processing shows a walking fox moving left to right along a blue progress bar, with the current step and an estimated time remaining for measurable steps. Estimates use the observed processing rate and may change with page complexity. Validation, topic matching, and final compression show “Estimating…” when no reliable estimate is available. The bar reaches 100% only after the operation finishes; errors stop the fox. Reduced-motion preferences disable the walking animation.

The index editor keeps a fixed-height scrolling area and stable row order while you edit. Changing search/sort settings or explicitly replacing/restoring the index refreshes the view. Index edits apply immediately in the session; **Save changes** persists them in SQLite. Restore reloads saved edits. Index source **Auto** prefers **Sessions & course plans** when numbered session headings exist. Session/grouped-session title pages become main entries; native-text course-plan active rows and Agenda/Contents lists supply subtopics, matched only inside their session. Native red rectangles identify active course-plan rows; no OCR or raster highlight detection is used. Repeated global course plans do not add every module under every session. “Next Session Plan” and “completed session” notices are ignored. Missing session numbers and unassigned modules remain visible for review, never assigned guessed session pages.

The editor, saved index, CSV, and index PDF retain session grouping. Sessions follow numeric order; topics sort alphabetically within each session. The index PDF uses a full-width table-of-contents layout with bold session headings, indented subtopics, dotted leaders, and page numbers aligned to the right margin. Edit the **Group / Heading** column to correct grouping; use **Type** `session` to add a missing main entry or `topic` for subtopics. Combined sessions share their actual title-page reference. Unmatched subtopics remain excluded with blank references until manually assigned and included. **Course plans** retains the flat course-outline mode; **Slide headings** retains the original extraction. **Use suggested index** explicitly replaces the current session index; saved edits remain restorable until you save again. Density controls suggested slide headings; **Add missing suggestions** adds them without replacing existing edits. Layout changes recalculate automatic references and flag manual references for review. Index links target the first referenced page in `ExamPrint.pdf`; cross-file links depend on the viewer. Keep both PDFs in one folder.

For books or subjects organized by a table of contents, choose **Table of contents** under **Index source**, then **Use suggested index**. Auto also chooses contents when no sessions are detected. Highlighted contents slides are checked first. For conventional TOCs, PDF bookmarks provide exact destinations when present; otherwise native-text Contents/Table of Contents pages are parsed, including dotted leaders, aligned page-number columns, and continuation pages. Titles are matched against document text. A page-number offset is inferred only when at least two matches agree; inferred references require review. Unmatched entries remain excluded with blank references. PDF page labels are also supported. Review all suggestions against your document, especially repeated titles and unusual layouts.

Repeated contents slides with one dark topic and faded alternatives are treated as topic-start markers. Native text color and opacity identify the active title; decorative numeric badges and known watermarks are ignored. Only the active topic gets that slide as its starting page. Repeated highlights retain the earliest start, and topics never highlighted remain excluded for manual assignment. Ambiguous slides are reported without guessing. Indented or decimal-numbered entries can become subtopics; a flat contents list does not imply parent-child relationships. Image-only highlights and other emphasis styles need manual review; this does not perform OCR.

Contents entries use **Type** `heading` or `subtopic` and **Group / Heading** for the parent heading, without requiring sessions. Deeper levels are flattened beneath their top-level heading. Headings print bold and subtopics indented; groups and their children sort alphabetically. References convert to handout pages using the slides-per-side setting. Saved edits and CSV/PDF exports retain the grouping. Scanned TOCs, wrapped entries, and complex multi-column layouts may need manual correction; OCR is not included.

No document content leaves the machine. Dependencies require installation, but runtime needs no network, API keys, OCR, or language model. Topic extraction uses native text and heading heuristics; image-only pages require manual topics. Review suggested headings and small print sizes before printing.

Local metadata, extracted headings, and saved edits are in `data/examprint.sqlite3`; uploaded binaries are never stored there. Set `EXAMPRINT_DB` to choose another database path. Temporary PDFs use the operating system temporary directory and are removed when the session workspace is released or **Clear session and temporary PDFs** is selected. A process crash can leave OS temporary files. Clearing a session retains saved database records.

The upload limit defaults to 250 MB. Set `EXAMPRINT_MAX_UPLOAD_MB` and Streamlit's `server.maxUploadSize` in `.streamlit/config.toml` to adjust it. The server binds to localhost and telemetry is disabled. Passwords stay in session memory. PDFs are validated, and embedded actions are not copied or executed.

Normal slides retain vector content; visible annotations and widgets are flattened on a temporary page copy. Preview processes at most three output pages. Full export is sequential and disk-backed; PDF object graphs and Streamlit download buffers still consume memory. Very large files need sufficient RAM. Text extraction skips embedded image decoding. Font fallback in the index may not support every complex script. No speed or memory benchmark is promised.

```bash
pytest -q
```

Tests generate temporary synthetic PDFs, including a 1,000-page document, and cover layout, preview parity, indexing, persistence, protected/corrupt inputs, annotations, and Streamlit workflows.
