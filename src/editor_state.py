"""Apply Streamlit's cumulative edits against a stable editor snapshot."""
from copy import deepcopy
from uuid import uuid4


def apply_editor_changes(baseline, visible, changes, added_ids):
    entries = {entry["id"]: deepcopy(entry) for entry in baseline}
    fields = {"Topic": "topic", "Printed Page": "printed_page_reference",
              "Session": "section", "Type": "kind"}
    for row_index, edits in changes.get("edited_rows", {}).items():
        entry = entries[visible[int(row_index)]["id"]]
        for column, field in fields.items():
            if column in edits:
                entry[field] = str(edits[column] or ("topic" if column == "Type" else "")).strip()
        if "Printed Page" in edits:
            entry["manually_edited"] = True
        if "Included" in edits:
            entry["included"] = bool(edits["Included"])
    for row_index in changes.get("deleted_rows", []):
        entries.pop(visible[int(row_index)]["id"], None)
    for index, row in enumerate(changes.get("added_rows", [])):
        entry_id = added_ids.setdefault(index, uuid4().hex)
        entries[entry_id] = dict(id=entry_id, topic=str(row.get("Topic", "") or "").strip(),
                                printed_page_reference=str(row.get("Printed Page", "") or "").strip(),
                                included=bool(row.get("Included", True)), manually_edited=True,
                                needs_review=False, source_pages=[], start_original_page=None, end_original_page=None,
                                section=str(row.get("Session", "") or "").strip(), kind=row.get("Type", "topic") or "topic")
    return list(entries.values())
