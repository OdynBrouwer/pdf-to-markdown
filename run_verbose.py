"""Run pdf2md with full debug logging enabled.

Usage:
    uv run python run_verbose.py --pdf_path in.pdf --out out/
    uv run python run_verbose.py --log-level INFO --pdf_path in.pdf
    uv run python run_verbose.py --log-level WARNING --pdf_path in.pdf
    uv run python run_verbose.py --pdf_path in.pdf --no-progress

Log levels: DEBUG (alles, default), INFO (per-pagina), WARNING, ERROR.

Because logging is configured BEFORE importing pdf2md, the loggers inside
pdfminer.six / pdfplumber inherit our settings automatically. The CLI routes
those records through the progress bar, so the two do not overwrite each other;
pass --no-progress (or --log-level DEBUG with a non-terminal stderr) for plain
line-by-line output.
"""

from __future__ import annotations

import argparse
import logging
import sys


# --- 1. Eigen argumenten parsen vóór pdf2md's argparse ---------------------


def _parse_log_args(argv: list[str]) -> tuple[str, list[str]]:
    """Haal --log-level eruit, geef (level, rest_van_argv) terug."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level for pdf2md / pdfminer / pdfplumber (default: DEBUG).",
    )
    known, remaining = parser.parse_known_args(argv)
    return known.log_level.upper(), remaining


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.DEBUG)

    # Root logger: dit is wat pdfminer/pdfplumber erven.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,  # overschrijf eventuele eerdere basicConfig
    )

    # Zorg dat de relevante namespaces minimaal op 'level' staan.
    for name in (
        "pdfminer",
        "pdfminer.pdfinterp",
        "pdfminer.converter",
        "pdfminer.layout",
        "pdfminer.cmapdb",
        "pdfplumber",
        "pdf2md",
    ):
        logging.getLogger(name).setLevel(level)

    # PIL is bijna altijd ruis, tenzij je expliciet DEBUG wilt.
    logging.getLogger("PIL").setLevel(
        logging.DEBUG if level == logging.DEBUG else logging.WARNING
    )


# --- 2. Main --------------------------------------------------------------


def main() -> int:
    level_name, passthrough = _parse_log_args(sys.argv[1:])
    _configure_logging(level_name)

    log = logging.getLogger("run_verbose")
    log.info("Log level = %s", level_name)
    log.debug("Passthrough args naar pdf2md: %r", passthrough)

    # Pas NU importeren, zodat pdfminer/pdfplumber onze logging erven.
    from pdf2md.cli import main as pdf2md_main

    return pdf2md_main(passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
