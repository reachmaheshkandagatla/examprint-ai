"""Extract index titles following a user-supplied literal PDF text marker."""
import re

from .pdf_engine import open_pdf
from .toc_index import page_rows


def extract_custom_topics(path, marker, password=None, status=None):
    marker = marker.strip()
    if not marker:
        raise ValueError("Enter a custom marker, such as Topic:.")
    # Markers are literal, not regular expressions. Avoid matching Topic: in Subtopic:.
    boundary = r"(?<!\w)" if marker[0].isalnum() else ""
    pattern = re.compile(boundary + re.escape(marker), re.IGNORECASE)
    topics, unavailable = {}, []
    empty_matches = 0
    with open_pdf(path, password) as doc:
        update = status.stage("Finding custom topic markers…", 0, .95) if status else None
        for index, page in enumerate(doc):
            rows = page_rows(page)
            if not rows:
                unavailable.append(index)
            for row in rows:
                text = row["text"]
                matches = list(pattern.finditer(text))
                for offset, match in enumerate(matches):
                    end = matches[offset + 1].start() if offset + 1 < len(matches) else len(text)
                    title = " ".join(text[match.end():end].split()).strip()
                    if not title:
                        empty_matches += 1
                        continue
                    entry = topics.setdefault(title.casefold(), {"topic": title, "source_pages": []})
                    if not entry["source_pages"] or entry["source_pages"][-1] != index:
                        entry["source_pages"].append(index)
            if update:
                update((index + 1) / len(doc))
    return {"custom_topics": list(topics.values()), "unavailable_pages": unavailable,
            "empty_matches": empty_matches}
