import pymupdf as fitz

from src.toc_index import extract_toc
from src.topic_extractor import extract_headings, suggested_topics
from src.index_engine import make_entries, remap_entries, export_index
from src.database import Database
from src.layout_engine import LayoutSettings


def contents_pdf(path):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), "Table of Contents", fontsize=20)
        for y, x, text in [(90, 40, "1 Foundations ........ 1"),
                           (120, 60, "1.1 Definitions ........ 2"),
                           (150, 60, "1.2 Examples ........ 3"),
                           (180, 40, "2 Missing ........ 99")]:
            page.insert_text((x, y), text)
        doc.new_page().insert_text((40, 40), "Cover")
        for title in ["Foundations", "Definitions", "Worked example"]:
            doc.new_page().insert_text((40, 40), title, fontsize=22)
        doc.save(path)


def test_contents_offset_review_and_export(tmp_path):
    path = tmp_path / "toc.pdf"
    contents_pdf(path)
    extraction = extract_headings(path)
    topics = suggested_topics(extraction, "Table of contents")
    assert suggested_topics(extraction) == topics
    assert [t['source_pages'] for t in topics] == [[2], [3], [4], []]
    assert [t['needs_review'] for t in topics] == [False, False, True, True]
    assert [t['kind'] for t in topics] == ['heading', 'subtopic', 'subtopic', 'heading']
    assert topics[1]['section'] == topics[0]['topic']
    entries = make_entries(topics, 2)
    assert [e['printed_page_reference'] for e in entries] == ['2', '2', '3', '']
    assert not entries[-1]['included']
    assert remap_entries(entries, 3)[2]['printed_page_reference'] == '2'
    entries[2]['needs_review'] = False
    output = tmp_path / 'index.pdf'
    export_index(entries, output, 3)
    with fitz.open(output) as doc:
        words = doc[0].get_text()
        assert words.index('1 Foundations') < words.index('1.1 Definitions')
        assert '1.2 Examples' in words and '2 Missing' not in words
        assert [link['page'] for link in doc[0].get_links()] == [1, 1, 2]
    db = Database(tmp_path / 'test.sqlite')
    document = db.register('toc.pdf', 'toc-hash', 5)
    db.save(document, LayoutSettings(), entries)
    _, restored = db.restore(document)
    assert {e['topic']: e['kind'] for e in restored} == {e['topic']: e['kind'] for e in entries}


def test_bookmarks_use_actual_destinations():
    with fitz.open() as doc:
        for _ in range(4):
            doc.new_page()
        doc.set_toc([[1, 'Foundations', 2], [2, 'Definitions', 3], [3, 'Details', 4]])
        topics = extract_toc(doc)['topics']
        assert [t['source_pages'] for t in topics] == [[1], [2], [3]]
        assert all(not t['needs_review'] for t in topics)
        assert topics[2]['section'] == 'Foundations'


def test_no_unproven_page_offset():
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), 'Contents')
        page.insert_text((40, 80), 'Unknown ........ 1')
        doc.new_page().insert_text((40, 40), 'Unrelated')
        topic = extract_toc(doc)['topics'][0]
        assert topic['source_pages'] == [] and topic['needs_review']


def test_continuation_and_separate_page_number_spans():
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), 'Contents')
        page.insert_text((40, 80), 'Main')
        page.insert_text((400, 80), '1')
        page = doc.new_page()
        page.insert_text((60, 80), 'Child A .... 2')
        page.insert_text((60, 110), 'Child B .... 3')
        for title in ['Main', 'Child A', 'Child B']:
            doc.new_page().insert_text((40, 40), title)
        result = extract_toc(doc)
        assert result['pages'] == [0, 1]
        assert [t['source_pages'] for t in result['topics']] == [[2], [3], [4]]
        assert result['topics'][-1]['section'] == 'Main'


def test_toc_source_in_app(tmp_path, monkeypatch):
    from io import BytesIO
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    path = tmp_path / 'lecture.pdf'
    contents_pdf(path)
    uploaded = BytesIO(path.read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = 'lecture.pdf', 'toc-upload', len(uploaded.getbuffer())
    monkeypatch.setattr(st, 'file_uploader', lambda *args, **kwargs: uploaded)
    monkeypatch.setenv('EXAMPRINT_DB', str(tmp_path / 'ui.sqlite'))
    app = AppTest.from_file('../app.py').run(timeout=20)
    assert not app.exception
    next(s for s in app.selectbox if s.label == 'Index source').set_value('Table of contents').run()
    next(b for b in app.button if b.label == 'Use suggested index').click().run()
    assert not app.exception
    assert app.session_state.entries[0]['kind'] == 'heading'
    assert app.session_state.entries[1]['kind'] == 'subtopic'
    next(b for b in app.button if b.label == 'Confirm reviewed page references').click().run()
    next(b for b in app.button if b.label == 'Generate selected index PDF').click().run()
    assert not app.exception and not app.error
    assert not next(d for d in app.get('download_button') if d.label == 'Download ExamIndex.pdf').disabled


def highlighted_slide(doc, active=(), opacity=False, numbered=True, children=False):
    page = doc.new_page(width=960, height=540)
    page.insert_text((35, 50), 'Table of Contents', fontsize=28, color=(.1, .05, .45))
    titles = ['Introduction to Deep Learning', 'Why Deep Learning?', 'Applications of Deep Learning']
    for index, title in enumerate(titles):
        x = 95 if children and index else 65
        y = 140 + index * 80
        color = (.18, .12, .72) if index in active or opacity else (.83, .82, .94)
        alpha = .18 if opacity and index not in active else 1
        if numbered:
            # Dark numeric badges must not count as highlighted topic text.
            page.insert_text((35, y), str(index + 1), fontsize=18)
        page.insert_text((x, y), title, fontsize=24, color=color, fill_opacity=alpha)
    page.insert_text((100, 450), 'S1-2026-27 Work Integrated Learning Programmes', fontsize=16)
    return page


def test_repeated_highlights_start_at_marker_not_first_contents(tmp_path):
    path = tmp_path / 'highlights.pdf'
    with fitz.open() as doc:
        highlighted_slide(doc, (0,))
        doc.new_page().insert_text((40, 40), 'Why Deep Learning?', fontsize=20)
        highlighted_slide(doc, (1,))
        highlighted_slide(doc, (1,))
        doc.save(path)
    extraction = extract_headings(path)
    topics = suggested_topics(extraction, 'Table of contents')
    assert extraction['toc']['method'] == 'Highlighted contents slides'
    assert [t['source_pages'] for t in topics] == [[0], [2], []]
    assert [t['needs_review'] for t in topics] == [False, False, True]
    assert len(topics) == 3
    assert topics[1]['topic'] == 'Why Deep Learning?'
    entries = make_entries(topics, 2)
    assert [e['printed_page_reference'] for e in entries] == ['1', '2', '']
    assert not entries[2]['included']
    assert suggested_topics(extraction) == topics
    output = tmp_path / 'index.pdf'
    export_index(entries, output, 2)
    with fitz.open(output) as pdf:
        assert 'Applications' not in pdf[0].get_text()
        assert {link['page'] for link in pdf[0].get_links()} == {0, 1}


def test_highlights_use_native_opacity_and_indented_children():
    with fitz.open() as doc:
        highlighted_slide(doc, (0,), opacity=True, numbered=True, children=True)
        highlighted_slide(doc, (1,), opacity=True, numbered=True, children=True)
        result = extract_toc(doc)
        assert [t['source_pages'] for t in result['topics']] == [[0], [1], []]
        assert [t['kind'] for t in result['topics']] == ['heading', 'subtopic', 'subtopic']
        assert result['topics'][1]['section'] == 'Introduction to Deep Learning'


def test_ambiguous_highlights_do_not_assign_any_topic():
    with fitz.open() as doc:
        highlighted_slide(doc, (0, 1))
        result = extract_toc(doc)
        assert result['ambiguous_pages'] == [0]
        assert all(not t['source_pages'] and t['needs_review'] for t in result['topics'])


def test_equal_color_repeated_lists_do_not_guess_first_topic():
    with fitz.open() as doc:
        highlighted_slide(doc, (0, 1, 2))
        highlighted_slide(doc, (0, 1, 2))
        result = extract_toc(doc)
        assert result['ambiguous_pages'] == [0, 1]
        assert all(not t['source_pages'] for t in result['topics'])


def test_highlighted_contents_app_export(tmp_path, monkeypatch):
    from io import BytesIO
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    path = tmp_path / 'highlighted.pdf'
    with fitz.open() as doc:
        highlighted_slide(doc, (0,))
        highlighted_slide(doc, (0, 1))  # Ambiguous: must be reported, not assigned.
        highlighted_slide(doc, (1,))
        doc.save(path)
    uploaded = BytesIO(path.read_bytes())
    uploaded.name, uploaded.file_id, uploaded.size = 'highlighted.pdf', 'highlight-upload', len(uploaded.getbuffer())
    monkeypatch.setattr(st, 'file_uploader', lambda *args, **kwargs: uploaded)
    monkeypatch.setenv('EXAMPRINT_DB', str(tmp_path / 'ui.sqlite'))
    app = AppTest.from_file('../app.py').run(timeout=20)
    assert not app.exception
    assert [e['source_pages'] for e in app.session_state.entries] == [[0], [2], []]
    assert any('No single active topic' in warning.value and '2' in warning.value for warning in app.warning)
    next(b for b in app.button if b.label == 'Generate selected index PDF').click().run()
    assert not app.exception and not app.error
    assert not next(d for d in app.get('download_button') if d.label == 'Download ExamIndex.pdf').disabled
