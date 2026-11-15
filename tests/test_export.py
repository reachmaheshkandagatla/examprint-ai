import zipfile
import pymupdf as fitz
import pytest
from src.export_engine import export_print, export_csv, export_zip
from src.index_engine import export_index, make_entries
from src.layout_engine import LayoutSettings
from src.pdf_engine import PDFError, validate_pdf, safe_filename
from src.preview_engine import generate_preview


def test_preview_matches_export(pdf_factory, tmp_path):
    source = pdf_factory(20, mixed=True)
    settings = LayoutSettings()
    full = export_print(source, tmp_path / "full.pdf", settings)
    preview = generate_preview(source, tmp_path / "preview.pdf", settings, start_slide=5)
    with fitz.open(full) as output, fitz.open(preview) as sample:
        assert len(sample) == 3
        for index, page in enumerate(sample):
            assert page.get_pixmap().samples == output[index + 1].get_pixmap().samples
    short = generate_preview(source, tmp_path / "last.pdf", settings, start_slide=20)
    with fitz.open(short) as doc:
        assert len(doc) == 1


def test_preview_only_visits_selected_slides(pdf_factory, tmp_path, monkeypatch):
    source = pdf_factory(100)
    calls = []
    original = fitz.Document.load_page
    def tracking(doc, index):
        if str(doc.name) == str(source):
            calls.append(index)
        return original(doc, index)
    monkeypatch.setattr(fitz.Document, "load_page", tracking)
    generate_preview(source, tmp_path / "preview.pdf", LayoutSettings(), start_slide=50)
    assert set(calls) == set(range(48, 57))


def test_thousand_pages(pdf_factory, tmp_path):
    progress = []
    path = export_print(pdf_factory(1000), tmp_path / "large.pdf", LayoutSettings(), progress=progress.append)
    with fitz.open(path) as doc:
        assert len(doc) == 334
        assert "Topic 1000" in doc[-1].get_text()
        assert doc[-1].get_text().strip().splitlines()[-1] == "334"
    assert len(progress) == 334 and progress[-1] == 1


@pytest.mark.parametrize("content", [b"", b"not a pdf", b"%PDF-1.7\ncorrupt"])
def test_bad_pdf(tmp_path, content):
    path = tmp_path / "bad.pdf"
    path.write_bytes(content)
    with pytest.raises(PDFError):
        validate_pdf(path)


def test_encrypted_pdf(pdf_factory, tmp_path):
    source = pdf_factory(1)
    protected = tmp_path / "protected.pdf"
    with fitz.open(source) as doc:
        doc.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
    with pytest.raises(PDFError):
        validate_pdf(protected)
    assert validate_pdf(protected, password="reader")["total_pages"] == 1
    export_print(protected, tmp_path / "unlocked.pdf", LayoutSettings(), password="reader")


def test_blank_page_export(tmp_path):
    path = tmp_path / "blank.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(path)
    result = export_print(path, tmp_path / "out.pdf", LayoutSettings())
    with fitz.open(result) as doc:
        assert len(doc) == 1
        assert doc[0].get_text().strip() == "1"


def test_annotation_preserved(pdf_factory, tmp_path):
    source = pdf_factory(1, annotations=True)
    path = export_print(source, tmp_path / "out.pdf", LayoutSettings())
    with fitz.open(path) as doc:
        assert len(doc) == 1
        # Visible content must survive even though active annotation objects do not.
        assert doc[0].get_images() or "ANNOTATION" in doc[0].get_text()
        assert not list(doc[0].annots())


def test_zip_csv_and_safe_filename(pdf_factory, tmp_path):
    entries = make_entries([{"topic": "Example", "source_pages": [0]}], 3)
    print_path = export_print(pdf_factory(1), tmp_path / "print.pdf", LayoutSettings())
    index_path = export_index(entries, tmp_path / "index.pdf", 1)
    export_csv(entries, tmp_path / "index.csv")
    assert "Topic,Printed Page" in (tmp_path / "index.csv").read_text(encoding="utf-8-sig")
    archive = export_zip(print_path, index_path, tmp_path / "both.zip")
    with zipfile.ZipFile(archive) as zip_file:
        assert zip_file.namelist() == ["ExamPrint.pdf", "ExamIndex.pdf"]
    assert safe_filename("../../secret.pdf") == "secret.pdf"
    assert safe_filename("C:\\folder\\lecture.pdf") == "lecture.pdf"


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_page_rotation_preserved(tmp_path, rotation):
    from src.layout_engine import fit_rect
    path = tmp_path / "rotated.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=960, height=540)
        for rect, color in [(fitz.Rect(0, 0, 480, 270), (1, 0, 0)),
                            (fitz.Rect(480, 0, 960, 270), (0, 1, 0)),
                            (fitz.Rect(0, 270, 480, 540), (0, 0, 1)),
                            (fitz.Rect(480, 270, 960, 540), (1, 1, 0))]:
            page.draw_rect(rect, color=None, fill=color)
        page.set_rotation(rotation)
        original = page.get_pixmap()
        source_rect = page.rect
        doc.save(path)
    output = export_print(path, tmp_path / "out.pdf", LayoutSettings())
    target = fit_rect(source_rect, LayoutSettings().slots()[0])
    with fitz.open(output) as doc:
        rendered = doc[0].get_pixmap()
        for x, y in [(.25, .25), (.75, .25), (.25, .75), (.75, .75)]:
            assert rendered.pixel(int(target.x0 + target.width * x), int(target.y0 + target.height * y)) == original.pixel(int(original.width * x), int(original.height * y))


def test_zero_page_pdf(tmp_path):
    path = tmp_path / "zero.pdf"
    path.write_bytes(b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF')
    with pytest.raises(PDFError, match="no pages"):
        validate_pdf(path)
