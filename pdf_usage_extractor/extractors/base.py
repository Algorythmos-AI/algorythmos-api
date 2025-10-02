from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..schemas import UsageRecord


class BaseExtractor(ABC):
    """Base class for provider specific extractors."""

    name: str = "base"
    provider_aliases: tuple[str, ...] = ()
    priority: int = 100

    def score(self, *, text: str, provider_hint: Optional[str]) -> float:
        """Return a score indicating how confident we are to handle the document."""
        score = 0.0
        if provider_hint:
            normalized = provider_hint.lower()
            if any(alias in normalized for alias in self.provider_aliases):
                score += 0.7
        score += self.detect_signal(text)
        return score

    def detect_signal(self, text: str) -> float:
        """Extractors can override to return a [0,1] signal from document text."""
        return 0.0

    @abstractmethod
    def extract(
        self,
        *,
        path: Path,
        text: str,
        debug: bool,
        logger: logging.Logger,
    ) -> Optional[UsageRecord]:
        """Return a UsageRecord if extraction succeeds."""

    def describe(self) -> str:
        return self.name
