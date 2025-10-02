from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class UsageRecord(BaseModel):
    provider: Optional[str] = Field(None, description="Detected provider")
    file: str
    invoice_date: Optional[date] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    internet_gb: Optional[float] = None
    currency: Optional[str] = None
    confidence: float = 0.0
    doc_type: Literal["telco_invoice", "invoice", "policy", "unknown"] = "unknown"

    @field_validator("internet_gb")
    @classmethod
    def _cap(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return value
        if value < 0 or value > 2000:
            raise ValueError("internet_gb out of expected range")
        return round(value, 3)


class ExtractResponse(BaseModel):
    count: int
    records: list[UsageRecord]
    warnings: list[str] = []
