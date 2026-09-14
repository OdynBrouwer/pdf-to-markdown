"""Command-line entry point.

Backward-compatible with the old script: `--pdf_path` still works. Adds `--out`,
`--config`, and `--progress` / `--no-progress`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import yaml

from .converter import DEFAULT_CONFIG, PdfToMarkdown
from .progress import TqdmProgress, progress_enabled


def _load_config(path: str | None) -> dict:
    candidate = Path(path) if path else Path("config/config.yaml")
    if candidate.is_file():
        with open(candidate, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


#: Toggles worth announcing at startup: config key -> label used in the summary.
_FEATURES = (
    ("extract_images", "images"),
    ("detect_borderless_tables", "borderless tables"),
    ("detect_blockquote", "blockquotes"),
    ("detect_footnotes", "footnotes"),
    ("bold_as_heading", "bold headings"),
)


def _feature_summary(config: dict) -> str:
    """One line naming the toggles that are on, so a run is never a black box."""
    on = [label for key, label in _FEATURES if config.get(key)]
    off = [label for key, label in _FEATURES if not config.get(key)]
    text = "features on: " + (", ".join(on) if on else "none")
    if off:
        text += f" | off: {', '.join(off)}"
    return text


@contextmanager
def _route_logging_through_progress(enabled: bool):
    """Keep log records from shredding the progress bar.

    tqdm's helper replaces the root handlers, so only engage it when the caller
    already configured logging (`run_verbose.py`, or a host app): switching it on
    unconditionally would start emitting records that used to go nowhere.
    """
    if not enabled or not logging.getLogger().handlers:
        yield
        return

    from tqdm.contrib.logging import logging_redirect_tqdm

    with logging_redirect_tqdm():
        yield


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdf2md",
        description="Convert a PDF file to Markdown (MIT-only, no AGPL/ML deps).",
        epilog=(
            "Progress bars need tqdm (`uv sync --extra progress`) and are only "
            "drawn when stderr is a terminal; use --progress to force one on."
        ),
    )
    parser.add_argument(
        "--pdf_path",
        required=True,
        help="Input PDF, or a folder: every *.pdf in it is converted one by one",
    )
    parser.add_argument(
        "--out",
        help=(
            "Output directory (default: a folder named after the PDF, beside it). "
            "With a folder of PDFs, each one gets its own subfolder here"
        ),
    )
    parser.add_argument("--config", help="Path to a YAML config file")
    parser.add_argument(
        "--progress",
        dest="progress",
        action="store_true",
        default=None,
        help="Force the progress bar on, even when stderr is not a terminal.",
    )
    parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        default=None,
        help="Never draw a progress bar (the default when stderr is redirected).",
    )
    args = parser.parse_args(argv)

    target = Path(args.pdf_path)
    if target.is_dir():
        pdfs = sorted(
            (p for p in target.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
            key=lambda p: p.name.lower(),
        )
        if not pdfs:
            print(f"error: no PDF files in {target}", file=sys.stderr)
            return 2
    elif target.is_file():
        pdfs = [target]
    else:
        print(f"error: file not found: {args.pdf_path}", file=sys.stderr)
        return 2

    config = _load_config(args.config)
    if args.out:
        config["OUTPUT_DIR"] = args.out

    show_progress = progress_enabled(force=args.progress)
    progress = TqdmProgress(enabled=show_progress)
    batch = target.is_dir()
    failed: list[str] = []

    with progress, _route_logging_through_progress(show_progress):
        progress.status(_feature_summary({**DEFAULT_CONFIG, **config}))
        for index, pdf in enumerate(pdfs, 1):
            file_config = dict(config)
            if batch and args.out:
                # One folder per document, so images from two PDFs can never
                # land on the same filename.
                file_config["OUTPUT_DIR"] = str(Path(args.out) / pdf.stem)
            if batch:
                progress.status(f"{index}/{len(pdfs)}: {pdf.name}")
            extractor = PdfToMarkdown(file_config, progress=progress)
            try:
                extractor.extract(str(pdf))
            except Exception as exc:
                if not batch:
                    raise
                failed.append(pdf.name)
                progress.status(f"FAILED {pdf.name}: {type(exc).__name__}: {exc}")
                continue
            out_md = Path(extractor.output_dir(str(pdf))) / f"{pdf.stem}.md"
            print(f"Wrote {out_md}")

    if failed:
        print(
            f"error: {len(failed)} of {len(pdfs)} failed: {', '.join(failed)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
