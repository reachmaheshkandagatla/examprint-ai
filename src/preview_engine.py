from pathlib import Path
import pymupdf as fitz
from .pdf_engine import open_pdf, render_sides, PDFError


def generate_preview(source_path, destination, settings, start_slide=1, password=None, status=None):
    with open_pdf(source_path, password) as source, fitz.open() as output:
        if not 1 <= start_slide <= len(source):
            raise PDFError("Starting slide is outside the document.")
        first_side = (start_slide - 1) // settings.slides_per_side
        progress = status.stage("Rendering preview pages…", 0, .9) if status else None
        render_sides(source, output, settings, first_side, 3, progress)
        if status:
            status.stage("Saving preview PDF…", .9, .99)
        output.save(destination, deflate=True)
    return Path(destination)


def render_preview_page(path, page_index=0, zoom=1.0):
    with fitz.open(path) as document:
        return document[page_index].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
