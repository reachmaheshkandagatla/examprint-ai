"""Offline heading heuristics, not semantic AI or OCR."""
from collections import Counter
import re
import pymupdf as fitz
from .pdf_engine import open_pdf
from .toc_index import extract_toc
from .session_index import text_lines, session_on_page, outline_on_page, highlighted_topics, session_topics

EXTRACTOR_VERSION = 5


def normalize_topic(text):
    text = re.sub(r"\s+", " ", text).strip(" \t•·–-:")
    return text[:240]


def extract_headings(path, password=None, progress=None, status=None):
    candidates, edges, textless = [], Counter(), []
    plans, sessions, outlines = [], [], []
    with open_pdf(path, password) as doc:
        toc_progress = status.stage("Scanning contents and bookmarks…", 0, .4) if status else None
        toc = extract_toc(doc, toc_progress)
        heading_progress = status.stage("Reading slide headings and course plans…", .4, .85) if status else None
        for index, page in enumerate(doc):
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)["blocks"]
            native_lines = text_lines(blocks)
            session = session_on_page(native_lines, index)
            if session and not any(s["numbers"] == session["numbers"] for s in sessions):
                sessions.append(session)
            plan_topics = course_plan_rows(page, blocks)
            if plan_topics is not None:
                plans.append({"page": index, "topics": plan_topics,
                              "active_topics": highlighted_topics(page, native_lines, plan_topics)})
            else:
                outline = outline_on_page(native_lines)
                if outline is not None:
                    outlines.append({"page": index, "topics": outline})
            lines = []
            for block in blocks:
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = normalize_topic(" ".join(s["text"] for s in spans))
                    if text:
                        lines.append((text, max(s["size"] for s in spans), line["bbox"][1],
                                      any(s["flags"] & 16 for s in spans)))
            if not lines:
                textless.append(index)
            sizes = sorted(size for text, size, y, bold in lines)
            median = sizes[len(sizes) // 2] if sizes else 0
            largest = max(sizes, default=0)
            page_edges = set()
            for text, size, y, bold in lines:
                key = text.casefold()
                edge = y < page.rect.height * .12 or y > page.rect.height * .88
                if edge:
                    page_edges.add(key)
                if 3 <= len(text) <= 180 and not re.fullmatch(r"[\d\W]+", text):
                    major = size >= largest * .95 and y < page.rect.height * .4
                    subtopic = size >= median * 1.15 or (bold and y < page.rect.height * .8)
                    granular = bold or size > median or (y < page.rect.height * .25 and len(text) < 90)
                    if major or subtopic or granular:
                        candidates.append({"topic": text, "page": index, "edge": edge,
                                           "rank": 0 if major else 1 if subtopic else 2})
            edges.update(page_edges)
            if progress:
                progress((index + 1) / len(doc))
            if heading_progress:
                heading_progress((index + 1) / len(doc))
        total_pages = len(doc)
        threshold = max(3, total_pages * .35)
    if status:
        status.stage("Matching topics to sessions and pages…", .85, .95)
    return {"headings": [c for c in candidates if not (c["edge"] and edges[c["topic"].casefold()] >= threshold)],
            "unavailable_pages": textless, "course_plans": plans, "toc": toc,
            "course_topics": course_plan_topics(plans, candidates),
            "sessions": sessions, "outlines": outlines,
            "session_topics": session_topics(sessions, plans, outlines, candidates, total_pages) if sessions else [],
            "missing_sessions": sorted(set(range(1, max((max(s["numbers"]) for s in sessions), default=0) + 1))
                                       - {n for s in sessions for n in s["numbers"]})}


def topics_from_headings(extraction, density="Balanced"):
    rank = {"Compact": 0, "Balanced": 1, "Detailed": 2}[density]
    topics = {}
    for heading in extraction["headings"]:
        if heading["rank"] <= rank:
            key = heading["topic"].casefold()
            entry = topics.setdefault(key, {"topic": heading["topic"], "source_pages": []})
            entry["source_pages"].append(heading["page"])
    return [{**entry, "source_pages": sorted(set(entry["source_pages"]))} for entry in topics.values()]


def topic_key(text):
    """Ignore punctuation and optional module labels when matching headings."""
    text = re.sub(r"^(?:m\s*\d+|module\s+\d+|\d+[.)])\s*[:.\-–]?\s*", "", text, flags=re.I)
    return " ".join(re.findall(r"\w+", text.casefold()))


def course_plan_rows(page, blocks=None):
    """Read horizontal text rows so separate module/topic PDF spans stay aligned."""
    rows = []
    for block in blocks if blocks is not None else page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)["blocks"]:
        for line in block.get("lines", []):
            if abs(line.get("dir", (1, 0))[1]) > .1:
                continue  # Ignore diagonal watermarks.
            spans = line.get("spans", [])
            text = normalize_topic(" ".join(s["text"] for s in spans))
            if text:
                rows.append({"text": text, "x": line["bbox"][0], "y": line["bbox"][1],
                             "bottom": line["bbox"][3], "size": max(s["size"] for s in spans)})
    titles = [r for r in rows if re.fullmatch(r"course\s+(?:plan|outline)|syllabus", r["text"], re.I)]
    if not titles:
        return None
    top = min(r["bottom"] for r in titles)
    body = sorted((r for r in rows if r["y"] > top), key=lambda r: (r["y"], r["x"]))
    groups = []
    for row in body:
        if groups and abs(groups[-1][0]["y"] - row["y"]) <= min(row["size"], groups[-1][0]["size"]) * .45:
            groups[-1].append(row)
        else:
            groups.append([row])
    numbered, plain = [], []
    for group in groups:
        text = normalize_topic(" ".join(r["text"] for r in sorted(group, key=lambda r: r["x"])))
        match = re.match(r"^(?:M\s*\d+|Module\s+\d+|\d+[.)])\s*[:.\-–]?\s+(.+)$", text, re.I)
        if match:
            numbered.append(normalize_topic(match[1]))
        elif (len(text) >= 3 and not re.search(r"watermark|integrated learning|programmes|copyright", text, re.I)
              and not re.fullmatch(r"[\d\W]+|module|topic|topics", text, re.I)):
            plain.append(text)
    return numbered or plain


def course_plan_topics(plans, headings):
    """Match plan topics to first actual lecture heading, never to the plan itself."""
    plan_pages = {p["page"] for p in plans}
    locations = {}
    for heading in headings:
        if heading["page"] not in plan_pages and heading["rank"] <= 1:
            locations.setdefault(topic_key(heading["topic"]), heading["page"])
    topics = {}
    for plan in plans:
        for title in plan["topics"]:
            key = topic_key(title)
            if key and key not in topics:
                page = locations.get(key)
                topics[key] = {"topic": title, "source_pages": [] if page is None else [page]}
    return list(topics.values())


def suggested_topics(extraction, source="Auto", density="Balanced"):
    if source == "Table of contents" or (source == "Auto" and extraction.get("toc", {}).get("topics") and not extraction.get("sessions")):
        return extraction.get("toc", {}).get("topics", [])
    if source == "Sessions & course plans" or (source == "Auto" and extraction.get("sessions")):
        return extraction.get("session_topics", [])
    if source == "Course plans" or (source == "Auto" and extraction.get("course_plans")):
        return extraction.get("course_topics", [])
    return topics_from_headings(extraction, density)
