import pymupdf as fitz
import pytest
from src.layout_engine import LayoutSettings, fit_rect, page_counts
from src.export_engine import export_print


def test_three_fit_a4():
    settings = LayoutSettings()
    slots = settings.slots()
    assert len(slots) == 3
    for slot in slots:
        assert fitz.Rect(0, 0, *settings.page_size).contains(slot)
    assert slots[0].y1 < slots[1].y0 < slots[2].y0


@pytest.mark.parametrize("count,expected", [(6, 2), (7, 3)])
def test_page_counts(pdf_factory, tmp_path, count, expected):
    output = export_print(pdf_factory(count), tmp_path / "out.pdf", LayoutSettings())
    with fitz.open(output) as doc:
        assert len(doc) == expected
        for index, page in enumerate(doc):
            assert page.get_text().strip().splitlines()[-1] == str(index + 1)
    assert page_counts(count, LayoutSettings()) == (expected, (expected + 1) // 2)


@pytest.mark.parametrize("per_side", [2, 3, 4, 6])
@pytest.mark.parametrize("orientation", ["Portrait", "Landscape"])
def test_aspect_and_containment(per_side, orientation):
    for original in (fitz.Rect(0, 0, 960, 540), fitz.Rect(0, 0, 400, 650)):
        for slot in LayoutSettings(per_side, orientation=orientation).slots():
            placed = fit_rect(original, slot)
            assert slot.contains(placed)
            assert placed.width / placed.height == pytest.approx(original.width / original.height)


def test_mixed_orientation(pdf_factory, tmp_path):
    output = export_print(pdf_factory(mixed=True), tmp_path / "out.pdf", LayoutSettings())
    with fitz.open(output) as doc:
        assert len(doc) == 3
        text = "".join(p.get_text() for p in doc)
        assert all(f"Topic {i}" in text for i in range(1, 8))
        assert text.count("WATERMARK") == 7
