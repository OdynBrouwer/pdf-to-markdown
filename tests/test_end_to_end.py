"""Golden end-to-end tests over committed fixture PDFs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pdf2md import PdfToMarkdown, convert_pdf
from pdf2md.cli import main as cli_main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fx(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.isfile(path):
        pytest.skip(f"fixture {name} not generated; run tests/fixtures/generate.py")
    return path


def test_basic_elements():
    md = convert_pdf(_fx("basic.pdf"))
    assert "# Document Title" in md
    assert "## Section One" in md
    assert "**bold**" in md
    assert "*italic*" in md
    assert "[Visit example.com](https://example.com)" in md
    assert "- First bullet" in md
    assert "  - Nested bullet" in md  # nesting via indentation
    assert "1. First step" in md
    assert "```python" in md
    assert "def greet(name):" in md
    # Heading text must not carry stray bold markers.
    assert "# **Document Title**" not in md


def test_table_is_gfm():
    md = convert_pdf(_fx("table.pdf"))
    assert "| Name" in md
    assert "| Ada" in md and "Engineer" in md
    sep = [ln for ln in md.splitlines() if set(ln) <= set("|- ") and "-" in ln]
    assert sep, "expected a GFM separator row"


def test_two_column_reading_order():
    md = convert_pdf(_fx("twocol.pdf"))
    assert "# Two Column Paper" in md
    # Title precedes body; entire left column precedes the right column.
    assert md.index("Two Column Paper") < md.index("Left column line 1")
    assert md.index("Left column line 12") < md.index("Right column line 1")
    # The two-column body must NOT be misread as a table.
    assert "|" not in md


def test_extract_writes_file(tmp_path):
    extractor = PdfToMarkdown({"OUTPUT_DIR": str(tmp_path)})
    full, pages = extractor.extract(_fx("basic.pdf"))
    out = tmp_path / "basic.md"
    assert out.is_file()
    assert out.read_text(encoding="utf-8").strip() == full.strip()
    assert len(pages) >= 1


def test_output_defaults_to_a_folder_named_after_the_pdf(tmp_path):
    """Without OUTPUT_DIR: <pdf_dir>/<name>/<name>.md, never the cwd."""
    pdf = tmp_path / "copy.pdf"
    pdf.write_bytes(Path(_fx("basic.pdf")).read_bytes())

    extractor = PdfToMarkdown({"extract_images": False})
    assert Path(extractor.output_dir(str(pdf))) == tmp_path / "copy"
    extractor.extract(str(pdf))
    assert (tmp_path / "copy" / "copy.md").is_file()


def test_explicit_output_dir_beats_the_pdf_folder(tmp_path):
    out = tmp_path / "elsewhere"
    pdf = tmp_path / "copy.pdf"
    pdf.write_bytes(Path(_fx("basic.pdf")).read_bytes())

    extractor = PdfToMarkdown({"OUTPUT_DIR": str(out), "extract_images": False})
    assert Path(extractor.output_dir(str(pdf))) == out
    extractor.extract(str(pdf))
    assert (out / "copy.md").is_file()


def test_cli_converts_every_pdf_in_a_folder(tmp_path):
    for name in ("one", "two"):
        (tmp_path / f"{name}.pdf").write_bytes(Path(_fx("basic.pdf")).read_bytes())
    (tmp_path / "notes.txt").write_text("not a pdf")

    assert cli_main(["--pdf_path", str(tmp_path), "--no-progress"]) == 0
    # Each document gets its own folder, next to its source PDF.
    assert (tmp_path / "one" / "one.md").is_file()
    assert (tmp_path / "two" / "two.md").is_file()


def test_cli_folder_of_pdfs_respects_out_dir(tmp_path):
    for name in ("one", "two"):
        (tmp_path / f"{name}.pdf").write_bytes(Path(_fx("basic.pdf")).read_bytes())
    out = tmp_path / "converted"

    args = ["--pdf_path", str(tmp_path), "--out", str(out), "--no-progress"]
    assert cli_main(args) == 0
    # ... still one folder per document, so images cannot collide.
    assert (out / "one" / "one.md").is_file()
    assert (out / "two" / "two.md").is_file()


def test_cli_folder_without_pdfs_is_an_error(tmp_path):
    (tmp_path / "notes.txt").write_text("not a pdf")
    assert cli_main(["--pdf_path", str(tmp_path), "--no-progress"]) == 2


def test_cli_folder_walks_subfolders_by_default(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "one.pdf").write_bytes(Path(_fx("basic.pdf")).read_bytes())
    (sub / "two.pdf").write_bytes(Path(_fx("basic.pdf")).read_bytes())

    assert cli_main(["--pdf_path", str(tmp_path), "--no-progress"]) == 0
    assert (tmp_path / "one" / "one.md").is_file()
    assert (sub / "two" / "two.md").is_file()


def test_cli_no_recursive_stays_on_the_top_level(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "one.pdf").write_bytes(Path(_fx("basic.pdf")).read_bytes())
    (sub / "two.pdf").write_bytes(Path(_fx("basic.pdf")).read_bytes())

    args = ["--pdf_path", str(tmp_path), "--no-progress", "--no-recursive"]
    assert cli_main(args) == 0
    assert (tmp_path / "one" / "one.md").is_file()
    assert not (sub / "two").exists()
