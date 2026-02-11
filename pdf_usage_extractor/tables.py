from __future__ import annotations

from pathlib import Path
from typing import List

from .logging_utils import get_logger


def extract_table_text(path: Path, *, debug: bool = False) -> str:
    """Best-effort table text extraction via pdfplumber."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:  # pragma: no cover - dependency optional during tests
        return ""

    logger = get_logger(debug)
    table_chunks: List[str] = []

    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables() or []
                for table_index, raw_table in enumerate(tables, start=1):
                    rows = [" ".join(cell for cell in row if cell) for row in raw_table]
                    rendered = " | ".join(row for row in rows if row)
                    if rendered:
                        table_chunks.append(rendered)
                        if debug:
                            logger.debug(
                                "Captured table",
                                extra={
                                    "context": {
                                        "path": str(path),
                                        "page": page_index,
                                        "table": table_index,
                                        "preview": rendered[:120],
                                    }
                                },
                            )
    except Exception as exc:  # pragma: no cover - defensive, library specific
        logger.warning(
            "Table extraction failed",
            extra={"context": {"path": str(path), "error": type(exc).__name__}},
        )
        return ""

    return "\n".join(table_chunks)
