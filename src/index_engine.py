"""Index references remain independent of the index PDF's own pagination."""
import re
from uuid import uuid4
from pathlib import Path
import pymupdf as fitz
from .layout_engine import printed_page


def format_ranges(pages):
    values = sorted(set(pages))
    groups = []
    for value in values:
        if groups and value == groups[-1][-1] + 1:
            groups[-1].append(value)
        else:
            groups.append([value])
    return ", ".join(str(g[0]) if len(g) == 1 else f"{g[0]}–{g[-1]}" for g in groups)


def parse_reference(reference, total_pages):
    if reference is None or not str(reference).strip():
        raise ValueError("Printed page is blank. Enter a page number or exclude this topic.")
    pages = set()
    for part in str(reference).split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?:[-–]\s*(\d+)\s*)?", part)
        if not match:
            raise ValueError("Use page numbers or ranges, such as 2, 5–8.")
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= total_pages:
            raise ValueError(f"Page references must be between 1 and {total_pages}.")
        pages.update(range(start, end + 1))
    return sorted(pages)


def make_entries(topics, slides_per_side):
    entries = []
    for topic in topics:
        pages = sorted(set(topic["source_pages"]))
        entries.append({"id": uuid4().hex, "topic": topic["topic"], "source_pages": pages,
                        "start_original_page": min(pages) if pages else None, "end_original_page": max(pages) if pages else None,
                        "printed_page_reference": format_ranges(printed_page(i, slides_per_side) for i in pages),
                        "manually_edited": not bool(pages), "included": bool(pages),
                        "needs_review": topic.get("needs_review", not bool(pages)),
                        "section": topic.get("section", ""), "kind": topic.get("kind", "topic")})
    return entries


def remap_entries(entries, slides_per_side):
    result = []
    for entry in entries:
        item = dict(entry)
        if item["manually_edited"]:
            item["needs_review"] = True
        else:
            item["printed_page_reference"] = format_ranges(printed_page(i, slides_per_side) for i in item["source_pages"])
        result.append(item)
    return result


def validate_entries(entries, total_pages, require_review=True):
    for entry in entries:
        if entry.get("kind", "topic") not in ("topic", "session", "heading", "subtopic"):
            raise ValueError("Entry type must be session, topic, heading, or subtopic.")
        if entry.get("kind") == "session" and not entry.get("section", "").strip():
            raise ValueError("Session headings need a Session label, such as Session 11.")
        if not entry["topic"].strip():
            raise ValueError("Topic names cannot be empty.")
        if entry["included"]:
            try:
                parse_reference(entry["printed_page_reference"], total_pages)
            except ValueError as exc:
                raise ValueError(f"{entry['topic']!r}: {exc}") from exc
            if require_review and entry.get("needs_review"):
                raise ValueError(f"Confirm the page reference and group assignment for {entry['topic']!r}, or exclude it from the index.")


def index_issues(entries, total_pages):
    """Report every selected invalid row, independently of review acknowledgement."""
    issues = []
    for entry in entries:
        if not entry["included"]:
            continue
        try:
            validate_entries([entry], total_pages, require_review=False)
        except ValueError as exc:
            issues.append({"id": entry["id"], "Session": entry.get("section", ""),
                           "Topic": entry["topic"], "Printed Page": entry["printed_page_reference"],
                           "Problem": str(exc)})
    return issues


def merge_entries(entries, selected_ids, name, total_pages):
    selected = [e for e in entries if e["id"] in selected_ids]
    if len(selected) < 2 or not name.strip():
        raise ValueError("Select at least two topics and supply a merged topic name.")
    if len({e.get("section", "") for e in selected}) > 1 or any(e.get("kind") in ("session", "heading") for e in selected):
        raise ValueError("Merge subtopics within one session or heading group; headings remain separate.")
    merged = dict(selected[0])
    merged.update(id=uuid4().hex, topic=name.strip(),
                  source_pages=sorted({p for e in selected for p in e["source_pages"]}),
                  printed_page_reference=format_ranges(p for e in selected for p in parse_reference(e["printed_page_reference"], total_pages)),
                  manually_edited=any(e["manually_edited"] for e in selected),
                  needs_review=any(e.get("needs_review", False) for e in selected),
                  included=any(e["included"] for e in selected))
    pages = merged["source_pages"]
    merged.update(start_original_page=min(pages) if pages else None, end_original_page=max(pages) if pages else None)
    return [e for e in entries if e["id"] not in selected_ids] + [merged]


def index_sort_key(entry):
    section = entry.get("section", "")
    number = re.match(r"Session\s+(\d+)", section, re.I)
    group = (0, int(number[1])) if number else (1, 0)
    return (*group, section.casefold(), 0 if entry.get("kind") in ("session", "heading") else 1, entry["topic"].casefold())


INDEX_FORMAT_VERSION = 3


def _wrap_index_text(text, font, size, width):
    lines, line = [], ""
    for word in str(text).split():
        candidate = (line + " " + word).strip()
        if font.text_length(candidate, fontsize=size) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ""
        for char in word:
            if line and font.text_length(line + char, fontsize=size) > width:
                lines.append(line)
                line = ""
            line += char
    return lines + ([line] if line else []) or [""]


def export_index(entries, destination, total_pages):
    included = sorted((e for e in entries if e["included"]), key=index_sort_key)
    validate_entries(included, total_pages)
    regular, bold, fallback = fitz.Font("helv"), fitz.Font("hebo"), fitz.Font("cjk")
    left, right, bottom = 42, 553, 790
    size, leading = 10, 14
    ink, muted = (.12, .16, .21), (.42, .46, .50)

    def choose_font(text, strong=False):
        font = bold if strong else regular
        return ("IndexBold" if strong else "IndexRegular", font) if all(font.has_glyph(ord(c)) for c in text) else ("IndexFallback", fallback)

    with fitz.open() as doc:
        def new_page():
            p = doc.new_page(width=595, height=842)
            for name, font in (("IndexRegular", regular), ("IndexBold", bold), ("IndexFallback", fallback)):
                p.insert_font(fontname=name, fontbuffer=font.buffer)
            p.insert_text((left, 41), "ExamPrint", fontname="IndexBold", fontsize=18, color=ink)
            p.insert_text((left, 59), "TOPIC INDEX", fontname="IndexRegular", fontsize=8, color=muted)
            p.insert_text((right - regular.text_length("PRINTED PAGE", fontsize=8), 59),
                          "PRINTED PAGE", fontname="IndexRegular", fontsize=8, color=muted)
            p.draw_line((left, 68), (right, 68), color=(.8, .82, .84), width=.5)
            label = str(len(doc))
            p.insert_text(((595 - regular.text_length(label, fontsize=9)) / 2, 818),
                          label, fontname="IndexRegular", fontsize=9, color=muted)
            return p

        page, y = new_page(), 91
        previous_section = None
        if not included:
            page.insert_text((left, y), "No topics included.", fontname="IndexRegular", fontsize=size)
        for position, entry in enumerate(included):
            section = entry.get("section", "")
            is_session = entry.get("kind") in ("session", "heading")
            new_section = bool(section and section != previous_section)
            show_section = new_section and not is_session
            if new_section and previous_section is not None:
                y += 8
            title = entry["topic"]
            reference = entry["printed_page_reference"]
            name, font = choose_font(title, is_session)
            ref_name, ref_font = choose_font(reference, is_session)
            x = left + (14 if section and not is_session else 0)
            ref_width = min(140, max(26, ref_font.text_length(reference, fontsize=size)))
            title_lines = _wrap_index_text(title, font, size, right - x - ref_width - 24)
            ref_lines = _wrap_index_text(reference, ref_font, size, ref_width)
            line_count = max(len(title_lines), len(ref_lines))
            extra = 20 if show_section else 0
            # Keep a session heading with at least the first line of its first subtopic.
            reserve = 18 if is_session and position + 1 < len(included) and included[position + 1].get("section") == section else 0
            if y + line_count * leading + extra + reserve > bottom and y > 91:
                page, y = new_page(), 91
                if section and not new_section and not is_session:
                    show_section = True
            if show_section:
                group_name, _ = choose_font(section, True)
                page.insert_text((left, y), section, fontname=group_name, fontsize=size, color=ink)
                y += 20
            previous_section = section
            # Align references with the final title line, including wrapped titles/ranges.
            title_lines += [""] * (line_count - len(title_lines))
            ref_lines = [""] * (line_count - len(ref_lines)) + ref_lines
            target_page = parse_reference(reference, total_pages)[0] - 1
            for offset, (title_line, ref_line) in enumerate(zip(title_lines, ref_lines)):
                if y > bottom:
                    page, y = new_page(), 91
                page.insert_text((x, y), title_line, fontname=name, fontsize=size, color=ink)
                if ref_line:
                    ref_x = right - ref_font.text_length(ref_line, fontsize=size)
                    page.insert_text((ref_x, y), ref_line, fontname=ref_name, fontsize=size, color=ink)
                    if offset == line_count - 1:
                        dot_start = x + font.text_length(title_line, fontsize=size) + 9
                        dot_end = ref_x - 9
                        dot_width = regular.text_length(".", fontsize=size)
                        count = max(0, int((dot_end - dot_start) / dot_width))
                        if count:
                            page.insert_text((dot_start, y), "." * count, fontname="IndexRegular", fontsize=size, color=muted)
                # One link per entry unless a very long entry crosses a page boundary.
                if offset == 0 or y == 91:
                    remaining = min(line_count - offset, int((bottom - y) // leading) + 1)
                    page.insert_link({"kind": fitz.LINK_GOTOR,
                                      "from": fitz.Rect(x, y - 11, right, y + (remaining - 1) * leading + 3),
                                      "file": "ExamPrint.pdf", "page": target_page, "to": fitz.Point(0, 0)})
                y += leading
            y += 4
        doc.subset_fonts()
        doc.save(destination, deflate=True, garbage=3)
    return Path(destination)
