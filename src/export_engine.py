from pathlib import Path
import csv
import zipfile
import pymupdf as fitz
from .pdf_engine import open_pdf, render_sides
from .index_engine import index_sort_key


def export_print(source_path, destination, settings, password=None, progress=None, status=None):
    destination = Path(destination)
    partial = destination.with_suffix(".partial.pdf")
    try:
        with open_pdf(source_path, password) as source, fitz.open() as output:
            render_progress = status.stage("Arranging slides on printed pages…", 0, .9) if status else progress
            render_sides(source, output, settings, progress=render_progress)
            if status:
                status.stage("Compressing and saving the print PDF…", .9, .99)
            output.save(partial, deflate=True, garbage=1)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


def export_csv(entries, destination):
    with open(destination, "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        group_label = "Group / Heading" if any(e.get("kind") in ("heading", "subtopic") for e in entries) else "Session"
        writer.writerow(["Topic", "Printed Page", "Included", "Needs Review", group_label, "Type"])
        for entry in sorted(entries, key=index_sort_key):
            writer.writerow([entry["topic"], entry["printed_page_reference"], entry["included"], entry.get("needs_review", False), entry.get("section", ""), entry.get("kind", "topic")])
    return Path(destination)


def export_zip(print_path, index_path, destination):
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(print_path, "ExamPrint.pdf")
        archive.write(index_path, "ExamIndex.pdf")
    return Path(destination)
