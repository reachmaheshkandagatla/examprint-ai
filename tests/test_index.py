import pymupdf as fitz
import pytest
from src.database import Database
from src.index_engine import (make_entries, format_ranges, parse_reference, remap_entries,
                              merge_entries, validate_entries, export_index)
from src.layout_engine import LayoutSettings, printed_page
from src.topic_extractor import extract_headings, topics_from_headings


def test_mapping_and_ranges():
    assert [printed_page(i, 3) for i in range(7)] == [1, 1, 1, 2, 2, 2, 3]
    assert format_ranges([1, 2, 3, 5, 7, 8]) == "1–3, 5, 7–8"
    assert parse_reference("1–3, 5, 7-8", 8) == [1, 2, 3, 5, 7, 8]
    entries = make_entries([{"topic": "Topic", "source_pages": [0, 3, 6, 15]}], 3)
    assert entries[0]["printed_page_reference"] == "1–3, 6"


@pytest.mark.parametrize("ref", ["0", "3-1", "10", "oops", "1,", "1–999999999"])
def test_invalid_references(ref):
    with pytest.raises(ValueError):
        parse_reference(ref, 9)


def test_manual_persistence_and_remapping(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    doc_id = db.register("lecture.pdf", "abc", 12)
    entries = make_entries([{"topic": "Original", "source_pages": [0, 3, 6]},
                            {"topic": "Auto", "source_pages": [6, 9]}], 3)
    entries[0].update(topic="Renamed", printed_page_reference="2–3", manually_edited=True, included=False)
    db.save(doc_id, LayoutSettings(), entries)
    layout, loaded = db.restore(doc_id)
    assert layout == LayoutSettings()
    manual = next(e for e in loaded if e["topic"] == "Renamed")
    assert manual["printed_page_reference"] == "2–3" and not manual["included"]
    remapped = remap_entries(loaded, 6)
    assert next(e for e in remapped if e["topic"] == "Renamed")["needs_review"]
    assert next(e for e in remapped if e["topic"] == "Auto")["printed_page_reference"] == "2"
    db.save(doc_id, LayoutSettings(6), remapped)
    assert db.restore(doc_id)[1] == remapped


def test_review_blocks_index():
    entries = make_entries([{"topic": "Test", "source_pages": [0]}], 3)
    entries[0].update(manually_edited=True)
    remapped = remap_entries(entries, 6)
    with pytest.raises(ValueError, match="Confirm"):
        validate_entries(remapped, 1)


def test_merge():
    entries = make_entries([{"topic": "A", "source_pages": [0]}, {"topic": "B", "source_pages": [6]}], 3)
    merged = merge_entries(entries, [e["id"] for e in entries], "Combined", 3)
    assert len(merged) == 1
    assert merged[0]["printed_page_reference"] == "1, 3"
    assert remap_entries(merged, 6)[0]["printed_page_reference"] == "1–2"


def test_extraction_and_cache(pdf_factory, tmp_path):
    result = extract_headings(pdf_factory(12))
    assert not result["unavailable_pages"]
    topics = topics_from_headings(result)
    assert len(topics) == 12
    assert all(t["topic"].startswith("Topic") for t in topics)
    db = Database(tmp_path / "cache.sqlite")
    doc_id = db.register("a.pdf", "def", 12)
    db.cache_extraction(doc_id, 1, result)
    assert db.cached_extraction(doc_id, 1) == result
    assert db.cached_extraction(doc_id, 2) is None


def test_image_only_unavailable(tmp_path):
    path = tmp_path / "blank.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(path)
    result = extract_headings(path)
    assert result["unavailable_pages"] == [0]
    assert not topics_from_headings(result)


def test_index_pdf_unicode_and_links(tmp_path):
    entries = make_entries([{"topic": "Eigenvalues λ 中文", "source_pages": [0, 3, 6]},
                            {"topic": "Backpropagation", "source_pages": [9]}], 3)
    path = export_index(entries, tmp_path / "index.pdf", 4)
    with fitz.open(path) as doc:
        text = "".join(p.get_text() for p in doc)
        assert "Eigenvalues" in text and "中文" in text
        links = doc[0].get_links()
        assert len(links) == 2 and links[0]["kind"] == fitz.LINK_GOTOR
        assert links[0]["page"] == 3


def test_long_index_paginates(tmp_path):
    entries = make_entries([{"topic": f"Topic {i}: " + "long heading " * 8, "source_pages": [i]} for i in range(200)], 3)
    path = export_index(entries, tmp_path / "index.pdf", 67)
    with fitz.open(path) as doc:
        assert len(doc) > 1
        for page in doc:
            assert all(fitz.Rect(0, 0, 595, 842).contains(fitz.Rect(word[:4])) for word in page.get_text("words"))


def test_professional_index_alignment_and_leaders(tmp_path):
    entries = make_entries([
        {"topic": "Session 1 — Introduction to Machine Learning", "source_pages": [0], "section": "Session 1", "kind": "session"},
        {"topic": "Introduction", "source_pages": [0, 3, 6, 12], "section": "Session 1"},
        {"topic": "A longer topic " * 12, "source_pages": [297], "section": "Session 1"},
    ], 3)
    path = export_index(entries, tmp_path / "professional.pdf", 100)
    with fitz.open(path) as doc:
        spans = [span for block in doc[0].get_text("dict")["blocks"] for line in block.get("lines", []) for span in line["spans"]]
        refs = [s for s in spans if s["text"] in ("1", "1–3, 5", "100") and s["bbox"][1] < 790]
        assert len(refs) == 3
        assert all(s["bbox"][2] == pytest.approx(553, abs=.1) for s in refs)
        leaders = [s for s in spans if len(s["text"]) > 3 and set(s["text"]) == {"."}]
        assert len(leaders) == 3
        assert any(s["text"].startswith("Session 1") and s["flags"] & 16 for s in spans)
        assert next(s for s in spans if s["text"] == "Introduction")["bbox"][0] == pytest.approx(56)
        for leader in leaders:
            ref = next(s for s in refs if abs(s["origin"][1] - leader["origin"][1]) < .1)
            assert leader["bbox"][2] < ref["bbox"][0]
        assert len(doc[0].get_links()) == 3


def test_legacy_layout_migration_preserves_saved_work(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite"
    db = Database(path)
    doc_id = db.register("lecture.pdf", "legacy", 7)
    entries = make_entries([{"topic": "Saved topic", "source_pages": [0, 3, 6]}], 3)
    db.save(doc_id, LayoutSettings(), entries)
    db.cache_extraction(doc_id, 5, {"headings": []})
    # Recreate the exact pre-one-slide constraint, retaining the saved rows.
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            ALTER TABLE layout_settings RENAME TO legacy_layout;
            CREATE TABLE layout_settings (
                document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                slides_per_side INTEGER NOT NULL CHECK(slides_per_side IN (2,3,4,6)),
                paper_size TEXT NOT NULL, orientation TEXT NOT NULL, margin REAL NOT NULL, spacing REAL NOT NULL);
            INSERT INTO layout_settings SELECT * FROM legacy_layout;
            DROP TABLE legacy_layout;
        ''')
    migrated = Database(path)
    assert migrated.restore(doc_id) == (LayoutSettings(), entries)
    assert migrated.cached_extraction(doc_id, 5) == {"headings": []}
    one_slide = remap_entries(entries, 1)
    assert one_slide[0]["printed_page_reference"] == "1, 4, 7"
    migrated.save(doc_id, LayoutSettings(slides_per_side=1), one_slide)
    assert Database(path).restore(doc_id) == (LayoutSettings(slides_per_side=1), one_slide)


@pytest.mark.parametrize("sort_alpha", [True, False])
def test_numbered_topic_order_in_pdf_csv_and_restore(tmp_path, sort_alpha):
    import csv
    from src.export_engine import export_csv
    titles = ["10. Optimization", "2. Vector Spaces", "1. Linear equations", "11. More optimization"]
    entries = make_entries([{"topic": title, "source_pages": [i]} for i, title in enumerate(titles)], 1)
    expected = [titles[i] for i in (2, 1, 0, 3)] if sort_alpha else titles
    pdf = export_index(entries, tmp_path / "ordered.pdf", 4, sort_alpha=sort_alpha)
    with fitz.open(pdf) as doc:
        text = doc[0].get_text()
        assert sorted(expected, key=text.index) == expected
    path = export_csv(entries, tmp_path / "ordered.csv", sort_alpha=sort_alpha)
    with open(path, encoding="utf-8-sig", newline="") as stream:
        assert [row[0] for row in list(csv.reader(stream))[1:]] == expected
    db = Database(tmp_path / "ordered.sqlite")
    document = db.register("ordered.pdf", "order", 4)
    db.save(document, LayoutSettings(slides_per_side=1), entries)
    assert [e["topic"] for e in db.restore(document)[1]] == titles


def test_natural_group_and_subtopic_order():
    from src.index_engine import index_sort_key
    entries = [
        {"topic": "Topic 10", "section": "Chapter 2"},
        {"topic": "Chapter 10", "section": "Chapter 10", "kind": "heading"},
        {"topic": "Topic 2", "section": "Chapter 2"},
        {"topic": "Chapter 2", "section": "Chapter 2", "kind": "heading"},
    ]
    assert [e["topic"] for e in sorted(entries, key=index_sort_key)] == [
        "Chapter 2", "Topic 2", "Topic 10", "Chapter 10"]
