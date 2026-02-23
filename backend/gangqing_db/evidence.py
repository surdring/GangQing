from __future__ import annotations

from typing import Any, Literal

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


EvidenceConfidenceLiteral = Literal["Low", "Medium", "High"]
EvidenceValidationLiteral = Literal[
    "verifiable",
    "not_verifiable",
    "out_of_bounds",
    "mismatch",
]


class EvidenceTimeRange(BaseModel):
    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def validate_end_after_start(cls, v: datetime, info):
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError("timeRange.end must be greater than timeRange.start")
        return v


class Evidence(BaseModel):
    evidence_id: str = Field(min_length=1, alias="evidenceId")
    source_system: str = Field(min_length=1, alias="sourceSystem")
    source_locator: dict[str, Any] = Field(alias="sourceLocator")
    time_range: EvidenceTimeRange = Field(alias="timeRange")
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    lineage_version: str | None = Field(default=None, alias="lineageVersion")
    data_quality_score: float | None = Field(default=None, alias="dataQualityScore")
    confidence: EvidenceConfidenceLiteral
    validation: EvidenceValidationLiteral
    redactions: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}

    @field_validator("data_quality_score")
    @classmethod
    def validate_data_quality_score_range(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0.0 or v > 1.0:
            raise ValueError("dataQualityScore must be in range 0.0..1.0")
        return v
