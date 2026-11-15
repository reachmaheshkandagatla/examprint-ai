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

The index editor keeps a fixed-height scrolling area and stable row order while you edit. Changing search/sort settings or explicitly replacing/restoring the index refreshes the view. Index edits apply immediately in the session; **Save changes** persists them in SQLite. Restore reloads saved edits. Index source **Auto** prefers **Sessions & course plans** when numbered session headings exist. Session/grouped-session title pages become main entries; native-text course-plan active rows and Agenda/Contents lists supply subtopics, matched only inside their session. Native red rectangles identify active course-plan rows; no OCR or raster highlight detection is used. Repeated global course plans do not add every module under every session. “Next Session Plan” and “completed session” notices are ignored. Missing session numbers and unassigned modules remain visible for review, never assigned guessed session pages.

The editor, saved index, CSV, and index PDF retain session grouping. Sessions follow numeric order; topics sort alphabetically within each session. The index PDF uses a full-width table-of-contents layout with bold session headings, indented subtopics, dotted leaders, and page numbers aligned to the right margin. Edit the **Session** column to correct grouping; use **Type** `session` to add a missing main entry or `topic` for subtopics. Combined sessions share their actual title-page reference. Unmatched subtopics remain excluded with blank references until manually assigned and included. **Course plans** retains the flat course-outline mode; **Slide headings** retains the original extraction. **Use suggested index** explicitly replaces the current session index; saved edits remain restorable until you save again. Density controls suggested slide headings; **Add missing suggestions** adds them without replacing existing edits. Layout changes recalculate automatic references and flag manual references for review. Index links target the first referenced page in `ExamPrint.pdf`; cross-file links depend on the viewer. Keep both PDFs in one folder.

No document content leaves the machine. Dependencies require installation, but runtime needs no network, API keys, OCR, or language model. Topic extraction uses native text and heading heuristics; image-only pages require manual topics. Review suggested headings and small print sizes before printing.

Local metadata, extracted headings, and saved edits are in `data/examprint.sqlite3`; uploaded binaries are never stored there. Set `EXAMPRINT_DB` to choose another database path. Temporary PDFs use the operating system temporary directory and are removed when the session workspace is released or **Clear session and temporary PDFs** is selected. A process crash can leave OS temporary files. Clearing a session retains saved database records.

The upload limit defaults to 250 MB. Set `EXAMPRINT_MAX_UPLOAD_MB` and Streamlit's `server.maxUploadSize` in `.streamlit/config.toml` to adjust it. The server binds to localhost and telemetry is disabled. Passwords stay in session memory. PDFs are validated, and embedded actions are not copied or executed.

Normal slides retain vector content; visible annotations and widgets are flattened on a temporary page copy. Preview processes at most three output pages. Full export is sequential and disk-backed; PDF object graphs and Streamlit download buffers still consume memory. Very large files need sufficient RAM. Text extraction skips embedded image decoding. Font fallback in the index may not support every complex script. No speed or memory benchmark is promised.

```bash
pytest -q
```

Tests generate temporary synthetic PDFs, including a 1,000-page document, and cover layout, preview parity, indexing, persistence, protected/corrupt inputs, annotations, and Streamlit workflows.
