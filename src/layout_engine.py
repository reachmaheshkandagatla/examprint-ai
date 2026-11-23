"""Shared, point-based geometry for preview and print output."""
from dataclasses import dataclass
from math import ceil
import pymupdf as fitz

MM = 72 / 25.4
FOOTER = 16


@dataclass(frozen=True)
class LayoutSettings:
    slides_per_side: int = 3
    paper_size: str = "A4"
    orientation: str = "Portrait"
    margin: float = 10.0
    spacing: float = 4.0

    def __post_init__(self):
        if self.slides_per_side not in (1, 2, 3, 4, 6):
            raise ValueError("Choose 1, 2, 3, 4, or 6 slides per side.")
        if self.paper_size != "A4" or self.orientation not in ("Portrait", "Landscape"):
            raise ValueError("Unsupported paper size or orientation.")
        if not 0 <= self.margin <= 40 or not 0 <= self.spacing <= 30:
            raise ValueError("Margins must be 0–40 mm and spacing 0–30 mm.")
        self.slots()

    @property
    def page_size(self):
        width, height = fitz.paper_size("a4")
        return (width, height) if self.orientation == "Portrait" else (height, width)

    def slots(self):
        width, height = self.page_size
        columns = 1 if self.slides_per_side in (1, 2, 3) else 2
        rows = self.slides_per_side // columns
        margin, gap = self.margin * MM, self.spacing * MM
        cell_w = (width - 2 * margin - (columns - 1) * gap) / columns
        cell_h = (height - 2 * margin - FOOTER - (rows - 1) * gap) / rows
        if min(cell_w, cell_h) < 20:
            raise ValueError("Margins and spacing leave too little room for slides.")
        return [fitz.Rect(margin + c * (cell_w + gap), margin + r * (cell_h + gap),
                          margin + c * (cell_w + gap) + cell_w,
                          margin + r * (cell_h + gap) + cell_h)
                for r in range(rows) for c in range(columns)]


def fit_rect(source, target):
    scale = min(target.width / source.width, target.height / source.height)
    width, height = source.width * scale, source.height * scale
    return fitz.Rect(max(target.x0, target.x0 + (target.width - width) / 2),
                     max(target.y0, target.y0 + (target.height - height) / 2),
                     min(target.x1, target.x0 + (target.width + width) / 2),
                     min(target.y1, target.y0 + (target.height + height) / 2))


def printed_page(original_index, slides_per_side):
    if original_index < 0 or slides_per_side not in (1, 2, 3, 4, 6):
        raise ValueError("Invalid page mapping.")
    return original_index // slides_per_side + 1


def page_counts(original_pages, settings):
    sides = ceil(original_pages / settings.slides_per_side)
    return sides, ceil(sides / 2)


def readability_warning(source_rect, settings):
    placed = fit_rect(source_rect, settings.slots()[0])
    if placed.width < 120 * MM or placed.height < 60 * MM:
        return "Small slide dimensions may make text difficult to read. Inspect the preview at print size."
    return None
