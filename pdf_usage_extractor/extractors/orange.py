from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

from ..schemas import UsageRecord
from .base import BaseExtractor

USAGE_AMOUNT_RE = re.compile(r"(\d+[.,]?\d*)\s*(Go|Mo)(?!\s*en\b)", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(\d+[.,]?\d*)\s*(Go|Mo)", re.IGNORECASE)
DATE_FACTURE_RE = re.compile(r"date de facture\s*:\s*(\d{2}/\d{2}/\d{2})", re.IGNORECASE)
ALT_DATE_RE = re.compile(r"votre facture mobile du\s*(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
PERIOD_RE = re.compile(
    r"période du\s*(\d{2}\.\d{2}\.\d{4})\s*au\s*(\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE,
)

OFFER_NOISE = (
    "votre offre",
    "appels/sms/mms",
    "go en fr métrop",
    "go en fr metrop",
    "eu/dom/suisse/andorre",
    "eu/dom",
    "suisse/andorre",
    "détails et conditions",
    "details et conditions",
    "forfait 170 go",
    "170 go",
    "100 go",
    "go en eu",
    "depuis les zones",
)


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def _to_float_gb(value_str: str, unit: str) -> float:
    value = float(value_str.replace(",", "."))
    return value if unit.lower() == "go" else value / 1024.0


def _usage_amounts(snippet: str, pattern: re.Pattern[str]) -> list[float]:
    return [_to_float_gb(v, u) for (v, u) in pattern.findall(snippet)]


def _looks_like_offer_block(text_block: str) -> bool:
    lowered = text_block.lower()
    lowered_na = _strip_accents(lowered)
    return any(item in lowered or item in lowered_na for item in OFFER_NOISE)


class OrangeExtractor(BaseExtractor):
    name = "orange"
    provider_aliases = ("orange", "orange france")
    priority = 5

    def detect_signal(self, text: str) -> float:
        lowered = text.lower()
        if "connexion" in lowered and "orange" in lowered:
            return 0.8
        if "facture" in lowered and "orange" in lowered:
            return 0.6
        if "orange" in lowered:
            return 0.4
        return 0.1 if "connexion" in lowered else 0.0

    def extract(
        self,
        *,
        path: Path,
        text: str,
        debug: bool,
        logger: logging.Logger,
    ) -> Optional[UsageRecord]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        lines_na = [_strip_accents(line.lower()) for line in lines]

        invoice_date = self._invoice_date(text)
        period_start, period_end = self._period(text)
        internet_gb, window_snippets = self._internet_usage(lines, lines_na, debug)

        if debug:
            for snippet in window_snippets:
                logger.debug(
                    "Matched window",
                    extra={"context": {"path": path.name, "window": snippet[:200]}},
                )

        if internet_gb is None:
            return None

        confidence = 0.6
        if invoice_date:
            confidence += 0.15
        if period_start and period_end:
            confidence += 0.15
        confidence = min(confidence, 0.95)

        return UsageRecord(
            provider="Orange",
            file=path.name,
            invoice_date=invoice_date,
            period_start=period_start,
            period_end=period_end,
            internet_gb=internet_gb,
            currency="EUR",
            confidence=round(confidence, 3),
            doc_type="telco_invoice",
        )

    @staticmethod
    def _invoice_date(text: str) -> Optional[dt.date]:
        match = DATE_FACTURE_RE.search(text)
        if match:
            return dt.datetime.strptime(match.group(1), "%d/%m/%y").date()
        match = ALT_DATE_RE.search(text)
        if match:
            return dt.datetime.strptime(match.group(1), "%d.%m.%Y").date()
        return None

    @staticmethod
    def _period(text: str) -> tuple[Optional[dt.date], Optional[dt.date]]:
        periods = PERIOD_RE.findall(text)
        if not periods:
            return None, None
        start_str, end_str = periods[-1]
        start = dt.datetime.strptime(start_str, "%d.%m.%Y").date()
        end = dt.datetime.strptime(end_str, "%d.%m.%Y").date()
        return start, end

    def _internet_usage(
        self,
        lines: list[str],
        lines_na: list[str],
        debug: bool,
    ) -> tuple[Optional[float], Iterable[str]]:
        windows: list[str] = []
        candidates: list[float] = []

        for idx, (_, normalized) in enumerate(zip(lines, lines_na)):
            if (
                "connexion" in normalized
                and "internet" in normalized
                and "france" in normalized
                and ("metropol" in normalized or "metropolitaine" in normalized)
            ):
                window = " | ".join(lines[idx : idx + 8])
                if not _looks_like_offer_block(window):
                    extracted = _usage_amounts(window, USAGE_AMOUNT_RE)
                    if extracted:
                        candidates.extend(extracted)
                        windows.append(window)

        if not candidates:
            for idx, normalized in enumerate(lines_na):
                if "internet" in normalized:
                    window = " | ".join(lines[idx : idx + 6])
                    if not _looks_like_offer_block(window):
                        extracted = _usage_amounts(window, USAGE_AMOUNT_RE)
                        if extracted:
                            candidates.extend(extracted)
                            windows.append(window)

        if not candidates:
            all_candidates = _usage_amounts("\n".join(lines), USAGE_AMOUNT_RE)
            filtered = [value for value in all_candidates if value < 120.0]
            candidates = filtered or all_candidates

        internet_gb = max(candidates) if candidates else None
        if internet_gb is None:
            return None, windows

        if debug:
            windows.extend(self._fallback_windows(lines, candidates))
        return internet_gb, windows

    @staticmethod
    def _fallback_windows(lines: list[str], candidates: Iterable[float]) -> list[str]:
        rendered = []
        joined = "\n".join(lines)
        for value in candidates:
            token = f"{value:.3f}" if value >= 1 else f"{value}"
            start = joined.find(token)
            if start == -1:
                continue
            snippet = joined[max(0, start - 40) : start + 40]
            rendered.append(snippet)
        return rendered
