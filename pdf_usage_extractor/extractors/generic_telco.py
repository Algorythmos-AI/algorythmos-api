from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

from dateutil import parser as date_parser

from ..schemas import UsageRecord
from .base import BaseExtractor

GENERIC_USAGE_RE = re.compile(r"(\d+[.,]?\d*)\s*(Go|Mo)", re.IGNORECASE)
GENERIC_PERIOD_RE = re.compile(
    r"période\s*(?:de|du)\s*(\d{2}[./]\d{2}[./]\d{2,4})\s*(?:au|à)\s*(\d{2}[./]\d{2}[./]\d{2,4})",
    re.IGNORECASE,
)
DATE_HINTS = (
    "date de facture",
    "date facture",
    "facture du",
    "bill date",
)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).replace("\u00a0", " ")


class GenericTelcoExtractor(BaseExtractor):
    name = "generic_telco"
    provider_aliases = ("telco", "generic")
    priority = 50

    def detect_signal(self, text: str) -> float:
        lowered = text.lower()
        if "internet" in lowered or "data" in lowered:
            return 0.3
        if "connexion" in lowered:
            return 0.2
        return 0.1 if "go" in lowered else 0.0

    def extract(
        self,
        *,
        path: Path,
        text: str,
        debug: bool,
        logger: logging.Logger,
    ) -> Optional[UsageRecord]:
        normalized = _normalize(text)
        internet_gb = self._internet_usage(normalized, debug, logger, path)
        invoice_date = self._invoice_date(normalized)
        period_start, period_end = self._period(normalized)

        if internet_gb is None:
            return None

        confidence = 0.3
        if invoice_date:
            confidence += 0.2
        if period_start and period_end:
            confidence += 0.2
        confidence = min(confidence, 0.75)

        return UsageRecord(
            provider=None,
            file=path.name,
            invoice_date=invoice_date,
            period_start=period_start,
            period_end=period_end,
            internet_gb=internet_gb,
            confidence=round(confidence, 3),
            doc_type="telco_invoice",
        )

    def _internet_usage(
        self,
        text: str,
        debug: bool,
        logger: logging.Logger,
        path: Path,
    ) -> Optional[float]:
        candidates: list[float] = []
        for match in GENERIC_USAGE_RE.findall(text):
            amount, unit = match
            value = float(amount.replace(",", "."))
            if unit.lower() == "mo":
                value /= 1024.0
            if value > 0 and value < 120:
                candidates.append(value)
        if not candidates:
            return None
        internet_gb = max(candidates)
        if debug:
            logger.debug(
                "Generic extractor candidates",
                extra={
                    "context": {
                        "path": path.name,
                        "candidates": candidates,
                        "selected": internet_gb,
                    }
                },
            )
        return internet_gb

    def _invoice_date(self, text: str) -> Optional[dt.date]:
        lowered = text.lower()
        for hint in DATE_HINTS:
            index = lowered.find(hint)
            if index == -1:
                continue
            snippet = text[index : index + 80]
            date_candidate = self._parse_date_from_snippet(snippet)
            if date_candidate:
                return date_candidate
        return self._parse_date_from_snippet(text[:120])

    @staticmethod
    def _parse_date_from_snippet(snippet: str) -> Optional[dt.date]:
        matches = re.findall(r"\d{2}[./]\d{2}[./]\d{2,4}", snippet)
        for match in matches:
            try:
                parsed = date_parser.parse(match, dayfirst=True).date()
                if parsed.year < 2035:
                    return parsed
            except (ValueError, OverflowError):
                continue
        return None

    def _period(self, text: str) -> tuple[Optional[dt.date], Optional[dt.date]]:
        match = GENERIC_PERIOD_RE.search(text)
        if not match:
            return None, None
        start_raw, end_raw = match.groups()
        try:
            start = date_parser.parse(start_raw, dayfirst=True).date()
            end = date_parser.parse(end_raw, dayfirst=True).date()
        except (ValueError, OverflowError):
            return None, None
        return start, end
