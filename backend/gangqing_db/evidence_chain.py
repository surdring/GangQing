from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from gangqing.common.errors import ErrorCode
from gangqing.common.evidence_messages import (
    claim_evidence_mismatch,
    numeric_claim_evidence_not_verifiable,
    lineage_version_required_for_computed_claim,
    evidence_update_conflict_detected,
)
from gangqing_db.evidence import Evidence, EvidenceValidationLiteral


ClaimTypeLiteral = Literal["number", "text", "table", "chart", "boolean"]


class EvidenceWarning(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str = Field(alias="requestId")

    model_config = {"populate_by_name": True}


class Claim(BaseModel):
    claim_id: str = Field(min_length=1, alias="claimId")
    claim_type: ClaimTypeLiteral = Field(alias="claimType")
    subject: str = Field(min_length=1)
    value: Any
    unit: str | None = None
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    lineage_version: str | None = Field(default=None, alias="lineageVersion")
    is_computed: bool = Field(default=False, alias="isComputed")
    validation: EvidenceValidationLiteral

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_numeric_claim_value(self) -> "Claim":
        if self.claim_type == "number":
            if not isinstance(self.value, (int, float)):
                raise ValueError("Numeric claim value must be a number")
        return self


class Citation(BaseModel):
    citation_id: str = Field(min_length=1, alias="citationId")
    evidence_id: str = Field(min_length=1, alias="evidenceId")
    source_system: str = Field(min_length=1, alias="sourceSystem")
    source_locator: dict[str, Any] = Field(alias="sourceLocator")
    time_range: dict[str, Any] = Field(alias="timeRange")
    extracted_at: str | None = Field(default=None, alias="extractedAt")
    filters_summary: dict[str, Any] | None = Field(default=None, alias="filtersSummary")

    model_config = {"populate_by_name": True}


class Lineage(BaseModel):
    metric_name: str = Field(min_length=1, alias="metricName")
    lineage_version: str = Field(min_length=1, alias="lineageVersion")
    formula_id: str | None = Field(default=None, alias="formulaId")
    inputs: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ToolCallTrace(BaseModel):
    tool_call_id: str = Field(min_length=1, alias="toolCallId")
    tool_name: str = Field(min_length=1, alias="toolName")
    status: Literal["success", "failure"]
    duration_ms: int | None = Field(default=None, alias="durationMs")
    args_summary: dict[str, Any] | None = Field(default=None, alias="argsSummary")
    result_summary: dict[str, Any] | None = Field(default=None, alias="resultSummary")
    error: dict[str, Any] | None = None
    evidence_refs: list[str] | None = Field(default=None, alias="evidenceRefs")

    model_config = {"populate_by_name": True}


class EvidenceChain(BaseModel):
    request_id: str = Field(min_length=1, alias="requestId")
    tenant_id: str = Field(min_length=1, alias="tenantId")
    project_id: str = Field(min_length=1, alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")

    claims: list[Claim] = Field(default_factory=list)
    evidences: list[Evidence] = Field(default_factory=list)
    citations: list[Citation] | None = None
    lineages: list[Lineage] | None = None
    tool_traces: list[ToolCallTrace] | None = Field(default=None, alias="toolTraces")
    warnings: list[EvidenceWarning] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class EvidenceChainValidationResult(BaseModel):
    evidence_chain: EvidenceChain = Field(alias="evidenceChain")
    can_output_deterministic_numbers: bool = Field(alias="canOutputDeterministicNumbers")

    model_config = {"populate_by_name": True}


def validate_evidence_chain(*, chain: EvidenceChain) -> EvidenceChainValidationResult:
    evidence_by_id: dict[str, Evidence] = {e.evidence_id: e for e in chain.evidences}

    warnings: list[EvidenceWarning] = list(chain.warnings)

    def _warn(*, code: ErrorCode, message: str, details: dict[str, Any] | None) -> None:
        warnings.append(
            EvidenceWarning(
                code=code.value,
                message=message,
                details=details,
                request_id=chain.request_id,
            )
        )

    can_output_deterministic_numbers = True

    for claim in chain.claims:
        if claim.claim_type == "number":
            if not claim.evidence_refs:
                can_output_deterministic_numbers = False
                claim.validation = "not_verifiable"
                _warn(
                    code=ErrorCode.EVIDENCE_MISSING,
                    message="Evidence missing for numeric claim",
                    details={"claimId": claim.claim_id},
                )
                continue

            missing_evidence_ids = [
                eid for eid in claim.evidence_refs if eid not in evidence_by_id
            ]
            if missing_evidence_ids:
                can_output_deterministic_numbers = False
                claim.validation = "not_verifiable"
                _warn(
                    code=ErrorCode.EVIDENCE_MISSING,
                    message="Evidence references not found for numeric claim",
                    details={
                        "claimId": claim.claim_id,
                        "missingEvidenceIds": missing_evidence_ids,
                    },
                )
                continue

            referenced_validations = [
                evidence_by_id[eid].validation for eid in claim.evidence_refs
            ]
            if any(v == "mismatch" for v in referenced_validations):
                can_output_deterministic_numbers = False
                claim.validation = "mismatch"
                _warn(
                    code=ErrorCode.EVIDENCE_MISMATCH,
                    message=claim_evidence_mismatch(),
                    details={"claimId": claim.claim_id, "evidenceRefs": claim.evidence_refs},
                )
            elif any(v != "verifiable" for v in referenced_validations):
                can_output_deterministic_numbers = False
                claim.validation = "not_verifiable"
                _warn(
                    code=ErrorCode.EVIDENCE_MISSING,
                    message=numeric_claim_evidence_not_verifiable(),
                    details={"claimId": claim.claim_id, "evidenceRefs": claim.evidence_refs},
                )

        if claim.is_computed and not (claim.lineage_version or "").strip():
            can_output_deterministic_numbers = False
            claim.validation = "not_verifiable"
            _warn(
                code=ErrorCode.EVIDENCE_MISSING,
                message=lineage_version_required_for_computed_claim(),
                details={"claimId": claim.claim_id, "missing": "lineageVersion"},
            )

    chain.warnings = warnings
    return EvidenceChainValidationResult(
        evidence_chain=chain,
        can_output_deterministic_numbers=can_output_deterministic_numbers,
    )


def merge_evidence_update(
    *,
    request_id: str,
    existing: Evidence,
    update: Evidence,
) -> tuple[Evidence, list[EvidenceWarning]]:
    if existing.evidence_id != update.evidence_id:
        raise ValueError("Evidence update evidenceId must match existing evidenceId")

    warnings: list[EvidenceWarning] = []

    def _warn(*, field: str, expected: Any, got: Any) -> None:
        warnings.append(
            EvidenceWarning(
                code=ErrorCode.EVIDENCE_MISMATCH.value,
                message=evidence_update_conflict_detected(),
                details={
                    "evidenceId": existing.evidence_id,
                    "field": field,
                    "expected": expected,
                    "got": got,
                },
                request_id=request_id,
            )
        )

    merged = existing.model_copy(deep=True)

    immutable_fields: list[tuple[str, Any, Any]] = [
        ("sourceSystem", existing.source_system, update.source_system),
        ("sourceLocator", existing.source_locator, update.source_locator),
        ("timeRange", existing.time_range, update.time_range),
        ("toolCallId", existing.tool_call_id, update.tool_call_id),
    ]
    for field, old_value, new_value in immutable_fields:
        if old_value != new_value:
            _warn(field=field, expected=old_value, got=new_value)

    if existing.lineage_version is None and update.lineage_version is not None:
        merged.lineage_version = update.lineage_version
    elif existing.lineage_version is not None and update.lineage_version is not None:
        if existing.lineage_version != update.lineage_version:
            _warn(field="lineageVersion", expected=existing.lineage_version, got=update.lineage_version)

    if existing.data_quality_score is None and update.data_quality_score is not None:
        merged.data_quality_score = update.data_quality_score
    elif existing.data_quality_score is not None and update.data_quality_score is not None:
        if existing.data_quality_score != update.data_quality_score:
            _warn(
                field="dataQualityScore",
                expected=existing.data_quality_score,
                got=update.data_quality_score,
            )

    confidence_rank = {"Low": 1, "Medium": 2, "High": 3}
    if confidence_rank.get(update.confidence, 0) > confidence_rank.get(existing.confidence, 0):
        merged.confidence = update.confidence
    elif update.confidence != existing.confidence:
        _warn(field="confidence", expected=existing.confidence, got=update.confidence)

    if existing.validation == "verifiable" and update.validation != "verifiable":
        _warn(field="validation", expected=existing.validation, got=update.validation)
    else:
        merged.validation = update.validation

    if update.redactions is None:
        return merged, warnings

    if merged.redactions is None:
        merged.redactions = dict(update.redactions)
        return merged, warnings

    merged_redactions = dict(merged.redactions)
    for k, v in update.redactions.items():
        if k not in merged_redactions:
            merged_redactions[k] = v
        else:
            if merged_redactions[k] != v:
                _warn(field=f"redactions.{k}", expected=merged_redactions[k], got=v)
    merged.redactions = merged_redactions
    return merged, warnings
