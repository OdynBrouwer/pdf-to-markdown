"""Progress reporting: callback contract, silent mode, CLI flag.

The pipeline must stay usable without a callback and without tqdm installed, so
these tests pin both the "reports every page of every stage" contract and the
degradation paths.
"""

from __future__ import annotations

import io
import os

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pdf2md import PdfToMarkdown
from pdf2md.cli import main as cli_main
from pdf2md.progress import (
    ONE_SHOT,
    STAGE_ANALYZE,
    STAGE_HEADERS,
    STAGE_IMAGES,
    STAGE_LOAD,
    STAGE_RENDER,
    STAGE_SERIALIZE,
    STAGE_STATS,
    TqdmProgress,
    progress_enabled,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
#: Steps with a page counter - these get a bar.
PAGE_STAGES = (STAGE_IMAGES, STAGE_LOAD, STAGE_ANALYZE, STAGE_RENDER)
#: One-off steps - these get a "[pdf2md] ..." line instead.
STEP_STAGES = (STAGE_STATS, STAGE_HEADERS, STAGE_SERIALIZE)


def _fx(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.isfile(path):
        pytest.skip(f"fixture {name} not generated; run tests/fixtures/generate.py")
    return path


def _multipage_pdf(tmp_path, pages=3):
    """A plain N-page PDF; every committed fixture is single-page."""
    path = tmp_path / "multipage.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    for i in range(pages):
        c.drawString(72, 720, f"Heading on page {i + 1}")
        c.drawString(72, 700, "Body text on this page.")
        c.showPage()
    c.save()
    return str(path)


def test_every_step_reports_itself(tmp_path):
    """No step may run invisibly: each one is a bar or an announcement."""
    calls = []
    extractor = PdfToMarkdown(
        {"OUTPUT_DIR": str(tmp_path)},
        progress=lambda stage, done, total: calls.append((stage, done, total)),
    )
    extractor.convert_to_markdown(_multipage_pdf(tmp_path, pages=3))

    for stage in PAGE_STAGES:
        per_stage = [(done, total) for s, done, total in calls if s == stage]
        # One call per page, counting 1..N, all against the same total.
        assert [done for done, _ in per_stage] == [1, 2, 3], stage
        assert {total for _, total in per_stage} == {3}, stage

    # Every other step announces itself once, in pipeline order.
    stepped = [stage for stage, _, total in calls if total == ONE_SHOT]
    assert stepped == list(STEP_STAGES)


def test_no_callback_is_fine():
    """The default stays callback-free so library users pay nothing."""
    doc = PdfToMarkdown({"extract_images": False}).convert(_fx("basic.pdf"))
    assert doc.pages


def test_progress_disabled_without_tty(monkeypatch):
    monkeypatch.delenv("PDF2MD_PROGRESS", raising=False)
    monkeypatch.delenv("PDF2MD_NO_PROGRESS", raising=False)
    assert progress_enabled(force=False) is False
    assert progress_enabled(stream=io.StringIO()) is False


def test_disabled_progress_is_silent():
    buf = io.StringIO()
    bar = TqdmProgress(enabled=False, stream=buf)
    with bar:
        bar(STAGE_LOAD, 1, 3)
        bar(STAGE_STATS, 0, ONE_SHOT)
        bar.status("features on: images")
    assert buf.getvalue() == ""


def test_progress_draws_bars_and_announces_steps():
    buf = io.StringIO()
    bar = TqdmProgress(stream=buf)
    if not bar.enabled:
        pytest.skip("tqdm not installed; run `uv sync --extra progress`")

    with bar:
        bar(STAGE_IMAGES, 1, 2)
        bar(STAGE_IMAGES, 2, 2)  # closes the "extracting images" bar
        bar(STAGE_STATS, 0, ONE_SHOT)  # announced, never drawn
        bar(STAGE_ANALYZE, 1, 1)
        bar.status("features on: images")

    out = buf.getvalue()
    assert "extracting images: 100%" in out
    assert "analyzing layout: 100%" in out
    assert "[pdf2md] measuring document" in out
    assert "[pdf2md] features on: images" in out
    assert out.endswith("\n")  # nothing left dangling


def test_cli_no_progress_writes_markdown(tmp_path):
    rc = cli_main(
        ["--pdf_path", _fx("basic.pdf"), "--out", str(tmp_path), "--no-progress"]
    )
    assert rc == 0
    assert (tmp_path / "basic.md").is_file()
