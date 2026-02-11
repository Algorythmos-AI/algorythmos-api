from __future__ import annotations

from typing import Optional

from .router import ExtractionRouter
from .schemas import UsageRecord

_ROUTER = ExtractionRouter()


def extract_path(input_path: str, provider_hint: Optional[str] = None) -> list[UsageRecord]:
    """Public convenience wrapper around the shared ExtractionRouter."""
    records, _ = _ROUTER.extract_path(input_path, provider_hint=provider_hint)
    return records


__all__ = ["extract_path", "ExtractionRouter", "UsageRecord"]
