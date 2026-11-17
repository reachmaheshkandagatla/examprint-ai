"""Read native-text contents pages and PDF outlines without assuming page offsets."""
from collections import Counter, defaultdict
import re
import pymupdf as fitz
from .session_index import NOISE

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
                lines.append((line["bbox"][1], line["bbox"][0], text, line["spans"]))
    rows = []
    for y, x, text, spans in sorted(lines, key=lambda item: (item[0], item[1])):
        if rows and abs(rows[-1]["y"] - y) <= 3:
            rows[-1]["text"] += " " + text
            rows[-1]["spans"].extend(spans)
        else:
            rows.append({"y": y, "x": x, "text": text, "spans": list(spans)})
    return rows


def row_ink(row):
    """Measure native text darkness on white, accounting for fill opacity.

    Numeric badges are decorative; only the title's letters vote.
    """
    total, weight = 0.0, 0
    for span in row["spans"]:
        count = sum(char.isalpha() for char in span["text"])
        color = span.get("color", 0)
        r, g, b = ((color >> shift) & 255 for shift in (16, 8, 0))
        darkness = (1 - (.2126 * r + .7152 * g + .0722 * b) / 255)
        total += count * darkness * span.get("alpha", 255) / 255
        weight += count
    return total / weight if weight else 0


def highlighted_contents(pages):
    """Recognize one dark active entry among faded entries on contents slides.

    A repeated contents list without a clear active row stays unassigned.
    Never use the other topics' presence as evidence of their start page.
    """
    slides = []
    for index, rows in enumerate(pages):
        title = next((row for row in rows if _TITLE.fullmatch(row["text"].strip())), None)
        if title is None:
            continue
        body = []
        for row in rows:
            text = row["text"].strip()
            if row["y"] <= title["y"] or NOISE.search(text) or not any(c.isalpha() for c in text):
                continue
            # Conventional contents entries have trailing destination numbers.
            if _ROW.fullmatch(text):
                continue
            text = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+|[•▪➢●]\s*)", "", text).strip()
            if len(text) >= 2:
                title_x = min(span["bbox"][0] for span in row["spans"] if any(c.isalpha() for c in span["text"]))
                body.append({**row, "x": title_x, "topic": text, "ink": row_ink(row)})
        if len(body) < 2:
            continue
        ordered = sorted(body, key=lambda row: row["ink"], reverse=True)
        active = None
        # Require one clearly dark row and faded alternatives, not a tiny color difference.
        if ordered[0]["ink"] >= .45 and ordered[1]["ink"] <= .35 and ordered[0]["ink"] - ordered[1]["ink"] >= .25:
            active = ordered[0]
        signature = tuple(title_key(row["topic"]) for row in body)
        slides.append((index, body, active, signature))
    counts = Counter(signature for _, _, _, signature in slides)
    topics, used_pages, ambiguous = {}, [], []
    for index, body, active, signature in slides:
        has_fading = min(row["ink"] for row in body) <= .35 and max(row["ink"] for row in body) >= .45
        if active is None and counts[signature] < 2 and not has_fading:
            continue
        used_pages.append(index)
        if active is None:
            ambiguous.append(index)
        left = min(row["x"] for row in body)
        section = ""
        for row in body:
            child = row["x"] > left + 10 or bool(re.match(r"^\s*\d+\.\d+", row["text"]))
            if not child:
                section = row["topic"]
            key = (title_key(section), title_key(row["topic"]))
            entry = topics.setdefault(key, {"topic": row["topic"], "section": section,
                                           "kind": "subtopic" if child else "heading",
                                           "source_pages": [], "needs_review": True})
            if row is active and not entry["source_pages"]:
                entry.update(source_pages=[index], needs_review=False)
    return {"topics": list(topics.values()), "pages": used_pages,
            "ambiguous_pages": ambiguous, "method": "Highlighted contents slides"}


def extract_toc(doc):
    """Use active contents slides, then explicit destinations or proven offsets.

    Unmatched references stay empty unless at least two heading matches agree
    on a single offset. Offset-only matches still require review.
    """
    pages = [page_rows(page) for page in doc]
    highlighted = highlighted_contents(pages)
    if highlighted["topics"] and any(topic["source_pages"] for topic in highlighted["topics"]):
        return highlighted
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

    if highlighted["topics"]:
        return highlighted
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
