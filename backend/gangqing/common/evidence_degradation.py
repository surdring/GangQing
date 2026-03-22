from __future__ import annotations

from dataclasses import dataclass

from gangqing.common.errors import ErrorCode
from gangqing.common.evidence_messages import (
    evidence_missing_for_tool_result,
    evidence_reference_not_found,
    evidence_mismatch_detected,
    guardrail_triggered_out_of_bounds,
    evidence_not_verifiable,
)
from gangqing_db.evidence import Evidence


@dataclass(frozen=True)
class EvidenceDegradationWarning:
    code: str
    message: str
    details: dict


@dataclass(frozen=True)
class EvidenceDegradationDecision:
    can_output_deterministic_numbers: bool
    warnings: list[EvidenceDegradationWarning]


def evaluate_evidence_degradation(
    *,
    tool_call_id: str | None,
    tool_name: str,
    evidence_refs: list[str] | None,
    evidences: list[Evidence],
) -> EvidenceDegradationDecision:
    warnings: list[EvidenceDegradationWarning] = []

    evidence_by_id = {e.evidence_id: e for e in evidences}

    can_output_deterministic_numbers = True

    if not evidence_refs:
        can_output_deterministic_numbers = False
        warnings.append(
            EvidenceDegradationWarning(
                code=ErrorCode.EVIDENCE_MISSING.value,
                message=evidence_missing_for_tool_result(),
                details={
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                },
            )
        )
        return EvidenceDegradationDecision(
            can_output_deterministic_numbers=can_output_deterministic_numbers,
            warnings=warnings,
        )

    for evidence_id in evidence_refs:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            can_output_deterministic_numbers = False
            warnings.append(
                EvidenceDegradationWarning(
                    code=ErrorCode.EVIDENCE_MISSING.value,
                    message=evidence_reference_not_found(),
                    details={
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "evidenceId": evidence_id,
                    },
                )
            )
            continue

        if evidence.validation == "verifiable":
            continue

        can_output_deterministic_numbers = False

        if evidence.validation == "mismatch":
            warnings.append(
                EvidenceDegradationWarning(
                    code=ErrorCode.EVIDENCE_MISMATCH.value,
                    message=evidence_mismatch_detected(),
                    details={
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "evidenceId": evidence_id,
                    },
                )
            )
            continue

        if evidence.validation == "out_of_bounds":
            warnings.append(
                EvidenceDegradationWarning(
                    code=ErrorCode.GUARDRAIL_BLOCKED.value,
                    message=guardrail_triggered_out_of_bounds(),
                    details={
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "evidenceId": evidence_id,
                    },
                )
            )
            continue

        warnings.append(
            EvidenceDegradationWarning(
                code=ErrorCode.EVIDENCE_MISSING.value,
                message=evidence_not_verifiable(),
                details={
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "evidenceId": evidence_id,
                },
            )
        )

    return EvidenceDegradationDecision(
        can_output_deterministic_numbers=can_output_deterministic_numbers,
        warnings=warnings,
    )
