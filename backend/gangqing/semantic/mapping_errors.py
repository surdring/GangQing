"""Error mapping module for mapping conflicts.

Maps ConflictDetectionResult to structured EVIDENCE_MISMATCH errors
with English messages, requestId, and retryable=false.
"""

from __future__ import annotations

from typing import Any, Dict

from gangqing.common.errors import AppError, ErrorCode, ErrorResponse
from gangqing.semantic.models.conflict_detection import (
    ConflictDetectionResult,
    ConflictType,
)


def map_conflict_to_error(
    conflict: ConflictDetectionResult,
    *,
    request_id: str,
    include_details: bool = True,
) -> AppError:
    """Map a conflict detection result to EVIDENCE_MISMATCH error.

    Args:
        conflict: The detected conflict
        request_id: Request ID for tracing (required per coding standards)
        include_details: Whether to include conflict details in error

    Returns:
        AppError with EVIDENCE_MISMATCH code and structured details
    """
    # Build English message based on conflict type
    message = _build_conflict_message(conflict)

    # Build structured details
    details: Dict[str, Any] = {
        "unified_id": conflict.unified_id,
        "entity_type": conflict.entity_type.value,
        "conflict_type": conflict.conflict_type.value,
        "severity": conflict.severity,
        "detected_at": conflict.detected_at.isoformat(),
    }

    if include_details and conflict.conflict_details:
        # Sanitize details - remove sensitive fields if needed
        safe_details = _sanitize_conflict_details(conflict.conflict_details)
        details["conflict_details"] = safe_details

    return AppError(
        code=ErrorCode.EVIDENCE_MISMATCH,
        message=message,
        request_id=request_id,
        details=details,
        retryable=False,  # Mapping conflicts are not retryable
    )


def _build_conflict_message(conflict: ConflictDetectionResult) -> str:
    """Build English error message for conflict type.

    Args:
        conflict: The detected conflict

    Returns:
        English error message
    """
    entity_type = conflict.entity_type.value
    unified_id = conflict.unified_id
    conflict_type = conflict.conflict_type

    if conflict_type == ConflictType.MULTI_TO_ONE:
        source_systems = conflict.conflict_details.get("source_systems", [])
        systems_str = ", ".join(source_systems) if source_systems else "multiple systems"
        return (
            f"Mapping conflict detected: MULTI_TO_ONE for {entity_type} {unified_id}. "
            f"Multiple source systems found: {systems_str}. "
            f"Aggregation blocked. Manual review required."
        )

    if conflict_type == ConflictType.CROSS_SYSTEM:
        source_system = conflict.conflict_details.get("source_system", "unknown")
        return (
            f"Mapping conflict detected: CROSS_SYSTEM for {entity_type} {unified_id}. "
            f"Conflict in source system: {source_system}. "
            f"Data quality issue detected."
        )

    if conflict_type == ConflictType.MAPPING_MISSING:
        return (
            f"Mapping conflict detected: MAPPING_MISSING for {entity_type} {unified_id}. "
            f"No mapping exists for this unified_id. "
            f"Please create mapping before aggregation."
        )

    if conflict_type == ConflictType.VERSION_MISMATCH:
        expected = conflict.conflict_details.get("expected_version", "unknown")
        actual = conflict.conflict_details.get("actual_version", "unknown")
        return (
            f"Mapping conflict detected: VERSION_MISMATCH for {entity_type} {unified_id}. "
            f"Expected version: {expected}, Actual version: {actual}. "
            f"Mapping has been modified."
        )

    # Default message for unknown conflict types
    return (
        f"Mapping conflict detected: {conflict_type.value} for {entity_type} {unified_id}. "
        f"Details: {conflict.conflict_details}"
    )


def _sanitize_conflict_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize conflict details to remove potentially sensitive information.

    Args:
        details: Raw conflict details

    Returns:
        Sanitized details safe for external exposure
    """
    # Copy to avoid mutating original
    safe = dict(details)

    # Remove internal fields that shouldn't be exposed
    sensitive_keys = {"internal_id", "db_record_id", "raw_query"}
    for key in sensitive_keys:
        safe.pop(key, None)

    return safe


def build_aggregation_blocked_error(
    unified_ids: list[str],
    entity_type: str,
    conflicts: list[ConflictDetectionResult],
    *,
    request_id: str,
) -> AppError:
    """Build error for aggregation blocked due to conflicts.

    Args:
        unified_ids: List of unified IDs that were being aggregated
        entity_type: Entity type string
        conflicts: List of detected conflicts
        request_id: Request ID for tracing

    Returns:
        AppError with EVIDENCE_MISMATCH code
    """
    conflict_types = list({c.conflict_type.value for c in conflicts})

    message = (
        f"Aggregation blocked due to mapping conflicts for {entity_type}. "
        f"Affected entities: {len(unified_ids)}. "
        f"Conflicts detected: {', '.join(conflict_types)}. "
        f"Resolve conflicts before retry."
    )

    details: Dict[str, Any] = {
        "unified_ids": unified_ids,
        "entity_type": entity_type,
        "conflict_count": len(conflicts),
        "conflict_types": conflict_types,
        "conflicts": [
            {
                "unified_id": c.unified_id,
                "conflict_type": c.conflict_type.value,
                "severity": c.severity,
            }
            for c in conflicts
        ],
    }

    return AppError(
        code=ErrorCode.EVIDENCE_MISMATCH,
        message=message,
        request_id=request_id,
        details=details,
        retryable=False,
    )


def error_response_to_dict(error: AppError) -> Dict[str, Any]:
    """Convert AppError to dictionary for JSON serialization.

    Args:
        error: The AppError to convert

    Returns:
        Dictionary representation of the error
    """
    response = error.to_response()
    return {
        "code": response.code,
        "message": response.message,
        "details": response.details,
        "retryable": response.retryable,
        "requestId": response.request_id,
    }
