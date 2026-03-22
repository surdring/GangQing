from __future__ import annotations


def evidence_missing_for_tool_result() -> str:
    return "Evidence missing for tool result"


def evidence_reference_not_found() -> str:
    return "Evidence reference not found"


def evidence_mismatch_detected() -> str:
    return "Evidence mismatch detected"


def guardrail_triggered_out_of_bounds() -> str:
    return "Evidence out of bounds; guardrail triggered"


def evidence_not_verifiable() -> str:
    return "Evidence is not verifiable"


def claim_evidence_mismatch() -> str:
    return "Evidence mismatch detected for claim"


def numeric_claim_evidence_not_verifiable() -> str:
    return "Evidence is not verifiable for numeric claim"


def lineage_version_required_for_computed_claim() -> str:
    return "Lineage version is required for computed claim"


def evidence_update_conflict_detected() -> str:
    return "Evidence update conflict detected"
