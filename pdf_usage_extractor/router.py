from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .extractors.generic_telco import GenericTelcoExtractor
from .extractors.orange import OrangeExtractor
from .extractors.base import BaseExtractor
from .io.pdf import load_text
from .logging_utils import get_logger
from .schemas import UsageRecord


class ExtractionRouter:
    """Orchestrate provider-specific extraction."""

    def __init__(self, extractors: Optional[Iterable[BaseExtractor]] = None) -> None:
        self.extractors: Tuple[BaseExtractor, ...] = (
            tuple(extractors) if extractors else (OrangeExtractor(), GenericTelcoExtractor())
        )

    def extract_path(
        self,
        input_path: str,
        *,
        provider_hint: Optional[str] = None,
        debug: bool = False,
    ) -> Tuple[List[UsageRecord], List[str]]:
        logger = get_logger(debug)
        start = time.perf_counter()

        resolved = Path(input_path).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Input path not found: {input_path}")

        pdf_files = self._collect_pdfs(resolved)
        records: List[UsageRecord] = []
        warnings: List[str] = []

        for pdf_path in pdf_files:
            try:
                text = load_text(str(pdf_path), debug=debug)
            except Exception as exc:  # pragma: no cover - defensive IO guard
                warning = f"FAILED_LOAD:{pdf_path.name}:{type(exc).__name__}"
                warnings.append(warning)
                logger.warning(
                    "Failed to load PDF",
                    extra={
                        "context": {
                            "path": str(pdf_path),
                            "error": type(exc).__name__,
                        }
                    },
                )
                continue

            record = self._extract_single(
                path=pdf_path,
                text=text,
                provider_hint=provider_hint,
                debug=debug,
                logger=logger,
            )

            if record:
                records.append(record)
            else:
                warning = f"NO_EXTRACTION:{pdf_path.name}"
                warnings.append(warning)
                logger.warning(
                    "Extraction failed",
                    extra={
                        "context": {
                            "path": str(pdf_path),
                            "provider_hint": provider_hint,
                        }
                    },
                )

        elapsed = time.perf_counter() - start
        avg_conf = round(
            sum(record.confidence for record in records) / len(records),
            3,
        ) if records else 0.0
        logger.info(
            "Extraction summary",
            extra={
                "context": {
                    "files": len(pdf_files),
                    "extracted": len(records),
                    "warnings": len(warnings),
                    "elapsed_sec": round(elapsed, 3),
                    "avg_confidence": avg_conf,
                }
            },
        )

        return records, warnings

    def _extract_single(
        self,
        *,
        path: Path,
        text: str,
        provider_hint: Optional[str],
        debug: bool,
        logger,
    ) -> Optional[UsageRecord]:
        scored = []
        for extractor in self.extractors:
            score = extractor.score(text=text, provider_hint=provider_hint)
            scored.append((score, extractor.priority, extractor))

        scored.sort(key=lambda item: (-item[0], item[1]))

        for score, _, extractor in scored:
            if score <= 0:
                continue
            try:
                record = extractor.extract(
                    path=path,
                    text=text,
                    debug=debug,
                    logger=logger,
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning(
                    "Extractor failure",
                    extra={
                        "context": {
                            "path": str(path),
                            "extractor": extractor.describe(),
                            "error": type(exc).__name__,
                        }
                    },
                )
                continue
            if record:
                record.confidence = max(record.confidence, round(min(score, 0.99), 3))
                if record.provider is None:
                    record.provider = extractor.name.replace("_", " ").title()
                return record

        return None

    @staticmethod
    def _collect_pdfs(path: Path) -> List[Path]:
        if path.is_file():
            if path.suffix.lower() != ".pdf":
                raise ValueError(f"Input must be a PDF: {path}")
            return [path]
        return sorted(p for p in path.rglob("*.pdf") if p.is_file())


_DEFAULT_ROUTER = ExtractionRouter()


def extract_path(input_path: str, provider_hint: Optional[str] = None) -> List[UsageRecord]:
    records, _ = _DEFAULT_ROUTER.extract_path(input_path, provider_hint=provider_hint)
    return records
