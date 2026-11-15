"""Session boundaries and conservative, session-local outline matching."""
import re
from difflib import SequenceMatcher

SESSION = re.compile(r"^session\s*(\d+(?:\s*(?:&|and|,|[-–])\s*\d+)*)\b\s*[:.\-–]?\s*(.*)$", re.I)
NOISE = re.compile(r"BITS|Generated:|copyright|watermark|integrated learning|programmes|@|faculty|instructor", re.I)
OUTLINE = re.compile(r"^(?:course\s+(?:plan|outline)|syllabus|agenda|contents|session\s+outline)$", re.I)


def clean(text):
    return re.sub(r"\s+", " ", text).strip(" \t•▪➢●–-:")


def key(text):
    text = re.sub(r"^(?:topic\s*:|module\s*[-–:]?|CS\s*[-–]?\d+\s*[-–:]?)\s*", "", text, flags=re.I)
    words = re.findall(r"\w+", text.casefold())
    return " ".join(w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words)


def text_lines(blocks):
    lines = []
    for block in blocks:
        for line in block.get("lines", []):
            if abs(line.get("dir", (1, 0))[1]) > .1:
                continue
            spans = line.get("spans", [])
            text = clean(" ".join(s["text"] for s in spans))
            if text and not NOISE.search(text):
                lines.append({"text": text, "rect": line["bbox"], "size": max(s["size"] for s in spans)})
    return sorted(lines, key=lambda line: (round(line["rect"][1], 1), line["rect"][0]))


def session_on_page(lines, page):
    for position, line in enumerate(lines):
        match = SESSION.match(line["text"])
        if not match:
            continue
        numbers = [int(n) for n in re.findall(r"\d+", match[1])]
        if any(n < 1 or n > 999 for n in numbers):
            continue
        if re.search(r"[-–]", match[1]) and len(numbers) == 2 and numbers[0] < numbers[1]:
            numbers = list(range(numbers[0], numbers[1] + 1))
        title = clean(match[2])
        if not title:
            for following in lines[position + 1:position + 4]:
                candidate = following["text"]
                if re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", candidate, re.I):
                    continue
                if not OUTLINE.fullmatch(candidate) and len(candidate) > 3:
                    title = candidate
                    break
        title = re.sub(r"^(?:topic\s*:|CS\s*[-–]?\d+\s*[-–:]?)\s*", "", title, flags=re.I)
        label = "Session " + " & ".join(str(n) for n in numbers)
        return {"label": label, "title": title, "numbers": numbers, "page": page}
    return None


def outline_on_page(lines):
    title = next((line for line in lines if OUTLINE.fullmatch(line["text"])), None)
    if title is None:
        # A module title immediately above a short bullet list is also an outline.
        title = next((line for line in lines if re.match(r"^Module\s*[-–:]", line["text"], re.I)), None)
    if title is None:
        return None
    result = []
    for line in lines:
        text = clean(re.sub(r"^(?:o\s+|[•▪➢●]\s*)", "", line["text"]))
        if line["rect"][1] <= title["rect"][1] or len(text) < 3 or re.fullmatch(r"\d+", text):
            continue
        if not re.fullmatch(r"M\s*\d+|module|topics?", text, re.I):
            result.append(text)
    return result


def highlighted_topics(page, lines, topics):
    """Recognize native red outline rectangles; no raster/OCR inference."""
    rectangles = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        if color and len(color) == 3 and color[0] > .7 and color[1] < .4 and color[2] < .4:
            rect = drawing["rect"]
            if rect.width > 50 and 10 < rect.height < page.rect.height * .3:
                rectangles.append(rect)
    selected = []
    for topic in topics:
        for line in lines:
            if key(topic) != key(line["text"]):
                continue
            x = (line["rect"][0] + line["rect"][2]) / 2
            y = (line["rect"][1] + line["rect"][3]) / 2
            if any(rect.x0 <= x <= rect.x1 and rect.y0 <= y <= rect.y1 for rect in rectangles):
                selected.append(topic)
                break
    return selected


def match_score(topic, heading):
    a, b = key(topic), key(heading)
    if a == b:
        return 1.0
    if a and b and (b.startswith(a + " ") or a.startswith(b + " ")):
        return .92
    # Tolerate minor wording changes, but never broad semantic guesses.
    aw, bw = set(a.split()), set(b.split())
    if len(aw) >= 2 and len(bw) >= 2 and len(aw & bw) / max(len(aw), len(bw)) >= .8:
        return .88
    if min(len(a), len(b)) > 12 and SequenceMatcher(None, a, b).ratio() >= .93:
        return .86
    return 0


def session_topics(sessions, plans, outlines, headings, total_pages):
    result, used = [], set()
    plan_pages = {p["page"] for p in plans} | {p["page"] for p in outlines}
    global_topics = {}
    for plan in plans:
        for topic in plan["topics"]:
            global_topics.setdefault(key(topic), topic)
    for index, session in enumerate(sessions):
        start = session["page"]
        stop = sessions[index + 1]["page"] if index + 1 < len(sessions) else total_pages
        section = session["label"]
        title = session["title"]
        result.append({"topic": f"{section} — {title}" if title else section,
                       "source_pages": [start], "section": section, "kind": "session"})
        # A repeated global plan is not a list of subtopics for every session.
        # Select only its active row or the module matching this session's title.
        local = {}
        for plan in plans:
            if start <= plan["page"] < min(stop, start + 10):
                selected = plan.get("active_topics", [])
                selected = selected or [t for t in plan["topics"] if match_score(t, title)]
                for topic in selected:
                    local[key(topic)] = (topic, start)
        for topic in global_topics.values():
            if match_score(topic, title):
                local.setdefault(key(topic), (topic, start))
        for outline in outlines:
            if start <= outline["page"] < min(stop, start + 10):
                for topic in outline["topics"]:
                    local.setdefault(key(topic), (topic, None))
        for topic_key, (topic, known_page) in local.items():
            if known_page is None:
                matches = [(match_score(topic, h["topic"]), h["page"]) for h in headings
                           if start <= h["page"] < stop and h["page"] not in plan_pages and h["rank"] <= 1]
                matches = [(score, page) for score, page in matches if score]
                if matches:
                    best = max(score for score, page in matches)
                    known_page = min(page for score, page in matches if score == best)
            result.append({"topic": topic, "source_pages": [] if known_page is None else [known_page],
                           "section": section, "kind": "topic"})
            used.add(topic_key)
    # Keep unmatched course modules visible without assigning them to a wrong session.
    for topic_key, topic in global_topics.items():
        if topic_key in used:
            continue
        matches = [h["page"] for h in headings if h["page"] not in plan_pages and key(h["topic"]) == topic_key]
        result.append({"topic": topic, "source_pages": [min(matches)] if matches else [],
                       "section": "Unassigned topics", "kind": "topic", "needs_review": True})
    return result
