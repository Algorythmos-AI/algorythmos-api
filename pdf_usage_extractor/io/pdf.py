from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Optional

import fitz  # type: ignore

from ..logging_utils import get_logger
from ..tables import extract_table_text


def load_text(path: str, *, use_ocr: bool = False, debug: bool = False) -> str:
    """Return normalized text for a PDF path.

    The file is read with PyMuPDF, NBSP is replaced with a plain space, and
    NFKC normalization is applied. Table text is appended when available.
    """
    logger = get_logger(debug)
    pdf_path = Path(path)
    if not pdf_path.exists():  # pragma: no cover - defensive guard
        raise FileNotFoundError(f"PDF not found: {path}")

    logger.debug("Loading PDF", extra={"context": {"path": str(pdf_path)}})

    with fitz.open(pdf_path) as doc:
        pages = [page.get_text("text") for page in doc]

    text = "\n".join(pages)
    normalized = unicodedata.normalize("NFKC", text).replace("\u00a0", " ")

    table_text = extract_table_text(pdf_path, debug=debug)
    if table_text:
        normalized = "\n".join([normalized, table_text])

    if use_ocr:
        logger.warning(
            "OCR fallback requested but not implemented; returning text only",
            extra={"context": {"path": str(pdf_path)}},
        )

    return normalized
