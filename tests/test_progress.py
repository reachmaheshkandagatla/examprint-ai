from src import progress as module
from src.progress import FoxProgress, progress_html


def test_eta_completion_and_failure(monkeypatch):
    now = [10.0]
    rendered = []
    class Slot:
        def html(self, value):
            rendered.append(value)
    monkeypatch.setattr(module.st, "empty", Slot)
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    with FoxProgress("Start") as progress:
        update = progress.stage("Reading pages", 0, .9)
        now[0] += 4
        update(.25)
        assert "12s" in rendered[-1]
        assert 'aria-valuenow="22"' in rendered[-1]
        update(1)
        progress.stage("Saving PDF", .9, .99)
        assert "Estimating" in rendered[-1]
        assert 'aria-valuenow="100"' not in rendered[-1]
    assert 'aria-valuenow="100"' in rendered[-1]
    assert "Finished in 4s" in rendered[-1]
    try:
        with FoxProgress("Start") as progress:
            progress.stage("Reading", 0, .9)(.5)
            raise ValueError("bad PDF")
    except ValueError:
        pass
    assert "Processing stopped" in rendered[-1]
    assert 'aria-valuenow="100"' not in rendered[-1]


def test_progress_markup_escapes_status_and_supports_reduced_motion():
    html = progress_html(.5, '<script>"oops"</script>', "Estimate")
    assert "<script>" not in html
    assert "prefers-reduced-motion" in html
    assert "left:50%" in html and "width:50%" in html


def test_extraction_reports_contents_before_headings(pdf_factory):
    from src.topic_extractor import extract_headings
    events = []
    class Status:
        def stage(self, label, start, end):
            events.append(label)
            return lambda fraction: events.append(fraction)
    extract_headings(pdf_factory(3), status=Status())
    assert events[0].startswith("Scanning contents")
    assert events[1:4] == [1 / 3, 2 / 3, 1]
    assert events[4].startswith("Reading slide headings")
    assert events[-1].startswith("Matching topics")


def test_progress_updates_all_tab_slots_and_remembers_last_status():
    outputs = [[], [], [], []]
    remembered = []
    class Slot:
        def __init__(self, output):
            self.output = output
        def html(self, value):
            self.output.append(value)
    with FoxProgress("Reading document…", slots=[Slot(output) for output in outputs],
                     on_update=remembered.append) as progress:
        progress.stage("Scanning contents", 0, .4)(1)
    assert all(output == remembered for output in outputs)
    assert "Complete · Reading document" in remembered[-1]
