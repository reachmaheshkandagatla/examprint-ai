from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
import pytest


@pytest.fixture
def pdf_factory(tmp_path):
    def create(count=7, mixed=False, annotations=False):
        path = tmp_path / f"source-{count}-{mixed}-{annotations}.pdf"
        with fitz.open() as doc:
            for index in range(count):
                width, height = (400, 650) if mixed and index % 2 else (960, 540)
                page = doc.new_page(width=width, height=height)
                page.insert_text((35, 50), f"Topic {index + 1}", fontsize=28)
                page.insert_text((35, 100), f"Body of slide {index + 1}", fontsize=12)
                page.insert_text((35, height - 30), "WATERMARK", fontsize=14)
                page.draw_rect(fitz.Rect(1, 1, width - 1, height - 1), color=(1, 0, 0))
                if annotations:
                    page.add_freetext_annot(fitz.Rect(100, 130, 260, 175), "ANNOTATION", fontsize=16)
            doc.save(path)
        return path
    return create
