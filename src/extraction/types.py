"""Typed models for structured extraction outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ExtractionKind = Literal["list_table", "detail_fields", "form_schema", "unknown"]
ExtractionStatus = Literal["success", "empty", "failed", "skipped"]


class EvidencePaths(BaseModel):
    screenshot: str = ""
    html: str = ""


class ExtractionResult(BaseModel):
    state_id: str
    target_id: str
    url: str = ""
    page_type: str = "unknown"
    capture_label: str = ""
    capture_context: str = ""
    strategy: ExtractionKind = "unknown"
    status: ExtractionStatus = "empty"
    confidence: float = 0.0
    records: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    evidence_paths: EvidencePaths = Field(default_factory=EvidencePaths)
    error: str = ""
