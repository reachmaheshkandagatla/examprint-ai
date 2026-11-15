"""Validated PDF access and sequential vector-preserving placement."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import re
import pymupdf as fitz
from .layout_engine import fit_rect, page_counts


class PDFError(ValueError):
    pass


def safe_filename(name):
    return re.sub(r"[^\w. -]", "_", name.replace("\\", "/").split("/")[-1])[:180] or "document.pdf"


def fingerprint(path):
    digest = sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def open_pdf(path, password=None):
    doc = None
    try:
        doc = fitz.open(path)
        if not doc.is_pdf:
            raise PDFError("The uploaded file is not a PDF.")
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise PDFError("This PDF requires a valid password.")
        if doc.page_count == 0:
            raise PDFError("The PDF has no pages.")
        yield doc
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as exc:
        raise PDFError("The PDF is corrupt or cannot be processed.") from exc
    finally:
        if doc is not None:
            doc.close()


def validate_pdf(path, max_bytes=250 * 1024 * 1024, password=None):
    size = Path(path).stat().st_size
    if size > max_bytes:
        raise PDFError(f"PDF exceeds the {max_bytes // (1024 * 1024)} MB upload limit.")
    with open_pdf(path, password) as doc:
        return {"total_pages": len(doc), "size": size, "file_hash": fingerprint(path)}


def render_sides(source, output, settings, first_side=0, side_count=None, progress=None):
    """Visit only requested input pages. Each output page is one printed side."""
    total, _ = page_counts(len(source), settings)
    if not 0 <= first_side < total:
        raise PDFError("Preview page is outside the document.")
    stop = total if side_count is None else min(total, first_side + side_count)
    slots = settings.slots()
    for side in range(first_side, stop):
        page = output.new_page(width=settings.page_size[0], height=settings.page_size[1])
        for slot_index, slot in enumerate(slots):
            index = side * settings.slides_per_side + slot_index
            if index >= len(source):
                break
            original = source.load_page(index)
            target = fit_rect(original.rect, slot)
            # Flatten visible annotation appearances on a one-page working copy.
            # The source and unannotated pages remain untouched.
            has_annotations = next(original.annots() or iter(()), None) is not None
            has_widgets = next(original.widgets() or iter(()), None) is not None
            if has_annotations or has_widgets:
                with fitz.open() as flattened:
                    flattened.insert_pdf(source, from_page=index, to_page=index, links=False)
                    flattened.bake(annots=True, widgets=True)
                    rotation = flattened[0].rotation
                    flattened[0].set_rotation(0)
                    page.show_pdf_page(target, flattened, 0, keep_proportion=True, rotate=-rotation)
            elif original.get_contents():
                rotation = original.rotation
                original.set_rotation(0)
                try:
                    page.show_pdf_page(target, source, index, keep_proportion=True, rotate=-rotation)
                except ValueError as exc:
                    if "nothing to show" not in str(exc).lower():
                        raise
                finally:
                    original.set_rotation(rotation)
        label = str(side + 1)
        label_width = fitz.get_text_length(label, fontsize=9)
        page.insert_text(((settings.page_size[0] - label_width) / 2, settings.page_size[1] - 6),
                         label, fontsize=9)
        if progress:
            progress((side - first_side + 1) / (stop - first_side))
