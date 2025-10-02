from __future__ import annotations

from datetime import date
from typing import Literal, Optional, Any, Dict

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


class ProcessorRunResponse(BaseModel):
    """Algorythmos-compatible processor run response."""
    
    run_id: str
    processor_name: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: str
    updated_at: Optional[str] = None
    tenant_id: str
    output: Optional[ExtractResponse] = None
    error: Optional[str] = None
    duration_sec: Optional[float] = None


class ProcessorCreateRunRequest(BaseModel):
    """Request to create a processor run."""
    
    input_path: str
    provider_hint: Optional[str] = None
    debug: bool = False
    webhook_url: Optional[str] = None


class ProcessorUpdateRequest(BaseModel):
    """Request to update a processor configuration."""
    
    description: Optional[str] = None
    confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    configuration: Optional[Dict[str, Any]] = None


class ProcessorInfo(BaseModel):
    """Processor information and configuration."""
    
    processor_name: str
    version: str
    updated_at: str
    status: str
    configuration: Dict[str, Any]
