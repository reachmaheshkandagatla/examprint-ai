"""Read native-text contents pages and PDF outlines without assuming page offsets."""
from collections import Counter, defaultdict
import re
import pymupdf as fitz

_TITLE = re.compile(r"(?:table\s+of\s+contents|contents)(?:\s*\(?continued\)?)?", re.I)
_ROW = re.compile(r"^(.+?)(?:\s*\.{2,}\s*|\s+)(\d+|[ivxlcdm]+)\s*$", re.I)


def title_key(text):
    text = re.sub(r"^(?:(?:chapter|unit|part)\s+)?\d+(?:\.\d+)*[.)]?\s+", "", text, flags=re.I)
    return " ".join(re.findall(r"\w+", text.casefold()))


def page_rows(page):
    """Join title and page-number spans sharing a baseline."""
    lines = []
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)["blocks"]:
        for line in block.get("lines", []):
            if abs(line.get("dir", (1, 0))[1]) > .1:
                continue
            text = " ".join(s["text"] for s in line["spans"]).strip()
            if text:
                lines.append((line["bbox"][1], line["bbox"][0], text))
    rows = []
    for y, x, text in sorted(lines):
        if rows and abs(rows[-1]["y"] - y) <= 3:
            rows[-1]["text"] += " " + text
        else:
            rows.append({"y": y, "x": x, "text": text})
    return rows


def extract_toc(doc):
    """Prefer explicit PDF destinations; otherwise match titles and infer proven offsets.

    Unmatched references stay empty unless at least two heading matches agree
    on a single offset. Offset-only matches still require review.
    """
    outline = doc.get_toc()
    if outline:
        topics, section = [], ""
        for level, title, destination in outline:
            if level == 1:
                section = title
            valid = 1 <= destination <= len(doc)
            topics.append({"topic": title, "section": section,
                           "kind": "heading" if level == 1 else "subtopic",
                           "source_pages": [destination - 1] if valid else [],
                           "needs_review": not valid})
        return {"topics": topics, "pages": [], "method": "PDF bookmarks"}

    pages = [page_rows(page) for page in doc]
    contents, toc_pages, continuing = [], set(), False
    for index, rows in enumerate(pages):
        titles = [i for i, row in enumerate(rows) if _TITLE.fullmatch(row["text"].strip())]
        body = rows[titles[0] + 1:] if titles else rows
        parsed = []
        for row in body:
            match = _ROW.fullmatch(row["text"])
            if match and re.search(r"[a-zA-Z]", match[1]):
                parsed.append({**row, "topic": match[1].strip(" .·"), "reference": match[2].lower()})
        # Untitled continuation pages must predominantly consist of TOC rows.
        if titles or (continuing and len(parsed) >= 2 and len(parsed) >= len(body) * .6):
            toc_pages.add(index)
            contents.extend(parsed)
            continuing = True
        else:
            continuing = False
    if not contents:
        return {"topics": [], "pages": sorted(toc_pages), "method": "Contents pages"}

    locations, labels = defaultdict(set), defaultdict(set)
    explicit_labels = bool(doc.get_page_labels())
    for index, rows in enumerate(pages):
        if index in toc_pages:
            continue
        if explicit_labels:
            labels[doc[index].get_label().lower()].add(index)
        for row in rows:
            locations[title_key(row["text"])].add(index)
    offsets = Counter()
    for row in contents:
        matches = locations[title_key(row["topic"])]
        if len(matches) == 1 and row["reference"].isdigit():
            offsets[next(iter(matches)) - (int(row["reference"]) - 1)] += 1
    offset = next(iter(offsets)) if len(offsets) == 1 and next(iter(offsets.values())) >= 2 else None
    left = min(row["x"] for row in contents)
    section, topics = "", []
    for row in contents:
        title, reference = row["topic"], row["reference"]
        is_child = row["x"] > left + 10 or bool(re.match(r"^\d+\.\d+", title))
        if not is_child:
            section = title
        matches = locations[title_key(title)]
        label_matches = labels[reference]
        destination, review = None, False
        if len(matches) == 1:
            destination = next(iter(matches))
            if label_matches and label_matches != matches:
                review = True
        elif len(label_matches) == 1:
            destination = next(iter(label_matches))
            review = True
        elif offset is not None and reference.isdigit():
            candidate = int(reference) - 1 + offset
            if 0 <= candidate < len(doc) and candidate not in toc_pages:
                destination, review = candidate, True
        topics.append({"topic": title, "section": section,
                       "kind": "subtopic" if is_child else "heading",
                       "source_pages": [] if destination is None else [destination],
                       "needs_review": review or destination is None})
    return {"topics": topics, "pages": sorted(toc_pages), "method": "Contents pages"}
