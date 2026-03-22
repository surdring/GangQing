"""Degradation/fallback strategy for mapping conflicts.

When conflicts are detected, the system degrades gracefully by returning
available data sources without aggregation. This module provides functions
to create degraded responses that preserve evidence chain integrity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from gangqing.semantic.models.conflict_detection import (
    ConflictDetectionResult,
    ConflictResolutionStrategy,
    ConflictType,
    DegradedResult,
)
from gangqing.semantic.models.entity_mapping import EntityMappingResponse


def create_degraded_response(
    conflict: ConflictDetectionResult,
    *,
    available_mappings: Optional[List[EntityMappingResponse]] = None,
    request_id: Optional[str] = None,
) -> DegradedResult:
    """Create a degraded response when mapping conflict is detected.

    Instead of returning aggregated data, this returns available data sources
    with conflict explanation for human review.

    Args:
        conflict: The detected conflict
        available_mappings: Optional list of available mappings (not aggregated)
        request_id: Request ID for tracing

    Returns:
        DegradedResult with available sources and conflict explanation
    """
    # Build list of available sources without aggregation
    available_sources: List[Dict[str, Any]] = []

    if available_mappings:
        for mapping in available_mappings:
            source_info = {
                "source_system": mapping.source_system,
                "source_id": mapping.source_id,
                "version": mapping.version,
                "valid_from": mapping.valid_from.isoformat(),
                # Include data availability status
                "data_available": True,  # Would be determined by actual data query
            }
            available_sources.append(source_info)
    elif conflict.conflict_details:
        # Build from conflict details if mappings not provided
        source_systems = conflict.conflict_details.get("source_systems", [])
        source_ids = conflict.conflict_details.get("source_ids", [])

        for i, system in enumerate(source_systems):
            source_id = source_ids[i] if i < len(source_ids) else "unknown"
            available_sources.append({
                "source_system": system,
                "source_id": source_id,
                "data_available": True,
            })

    # Build conflict summary
    conflict_summary = _build_degradation_summary(conflict)

    # Build recommended action
    recommended_action = _build_recommended_action(conflict)

    return DegradedResult(
        unified_id=conflict.unified_id,
        entity_type=conflict.entity_type,
        conflict_type=conflict.conflict_type,
        available_sources=available_sources,
        conflict_summary=conflict_summary,
        recommended_action=recommended_action,
        requires_manual_review=conflict.severity == "critical",
        detected_at=conflict.detected_at,
        request_id=request_id or conflict.request_id,
    )


def _build_degradation_summary(conflict: ConflictDetectionResult) -> str:
    """Build human-readable summary of the conflict.

    Args:
        conflict: The detected conflict

    Returns:
        Human-readable summary string
    """
    entity_type = conflict.entity_type.value
    unified_id = conflict.unified_id
    conflict_type = conflict.conflict_type
    severity = conflict.severity

    if conflict_type == ConflictType.MULTI_TO_ONE:
        systems = conflict.conflict_details.get("source_systems", [])
        systems_str = ", ".join(systems) if systems else "multiple systems"
        return (
            f"[{severity.upper()}] Cannot aggregate {entity_type} '{unified_id}' "
            f"due to multi-to-one mapping conflict. "
            f"The entity is mapped to multiple source IDs across: {systems_str}. "
            f"Aggregation would produce unreliable results. "
            f"Available sources are shown separately without aggregation."
        )

    if conflict_type == ConflictType.MAPPING_MISSING:
        return (
            f"[{severity.upper()}] Cannot aggregate {entity_type} '{unified_id}' "
            f"due to missing mapping. "
            f"No unified ID mapping exists for this entity. "
            f"Please create the mapping in the semantic layer before aggregation."
        )

    if conflict_type == ConflictType.CROSS_SYSTEM:
        source_system = conflict.conflict_details.get("source_system", "unknown")
        return (
            f"[{severity.upper()}] Cross-system conflict detected for {entity_type} '{unified_id}' "
            f"in {source_system}. "
            f"Data quality issue: source ID maps to multiple unified IDs. "
            f"Available sources are shown separately for manual review."
        )

    if conflict_type == ConflictType.VERSION_MISMATCH:
        expected = conflict.conflict_details.get("expected_version", "unknown")
        actual = conflict.conflict_details.get("actual_version", "unknown")
        return (
            f"[{severity.upper()}] Version mismatch for {entity_type} '{unified_id}'. "
            f"Expected mapping version {expected}, but current version is {actual}. "
            f"Mapping has been modified since expected version. "
            f"Please verify the correct version before aggregation."
        )

    # Default summary
    return (
        f"[{severity.upper()}] Mapping conflict detected for {entity_type} '{unified_id}'. "
        f"Conflict type: {conflict_type.value}. "
        f"Aggregation blocked. Available sources shown separately."
    )


def _build_recommended_action(conflict: ConflictDetectionResult) -> str:
    """Build recommended action for resolving the conflict.

    Args:
        conflict: The detected conflict

    Returns:
        Recommended action string
    """
    conflict_type = conflict.conflict_type

    if conflict_type == ConflictType.MULTI_TO_ONE:
        return (
            "RECOMMENDED ACTIONS: (1) Review mapping configuration to ensure "
            "each unified_id maps to exactly one source_id per system. "
            "(2) If intentional, document the multi-mapping with business justification. "
            "(3) For immediate resolution, manually select the correct source system."
        )

    if conflict_type == ConflictType.MAPPING_MISSING:
        return (
            "RECOMMENDED ACTIONS: (1) Create a mapping for this unified_id "
            "in the semantic mapping table. "
            "(2) Verify the source system and source_id are correct. "
            "(3) Contact data steward if the entity should exist but mapping is missing."
        )

    if conflict_type == ConflictType.CROSS_SYSTEM:
        return (
            "RECOMMENDED ACTIONS: (1) Investigate why source ID maps to multiple unified IDs. "
            "(2) Check for data quality issues in source system. "
            "(3) Consolidate or split mappings based on business logic. "
            "(4) Update mapping table to reflect correct relationship."
        )

    if conflict_type == ConflictType.VERSION_MISMATCH:
        return (
            "RECOMMENDED ACTIONS: (1) Reload mapping with current version. "
            "(2) Review mapping history to understand what changed. "
            "(3) If using cached mapping, clear cache and retry. "
            "(4) For concurrent modification, implement optimistic locking."
        )

    # Default recommendation
    return (
        "RECOMMENDED ACTIONS: (1) Review conflict details. "
        "(2) Contact semantic layer administrator. "
        "(3) Resolve underlying data quality issue before aggregation."
    )


def should_degrade(conflict: ConflictDetectionResult) -> bool:
    """Determine if a conflict should trigger degradation strategy.

    Degradation is applied for warning-level conflicts where we can
    still provide value by showing available sources separately.

    Args:
        conflict: The detected conflict

    Returns:
        True if degradation should be applied
    """
    # Critical conflicts require rejection, not just degradation
    if conflict.severity == "critical":
        return False

    # Multi-to-one and missing mappings must be rejected
    if conflict.conflict_type in (ConflictType.MULTI_TO_ONE, ConflictType.MAPPING_MISSING):
        return False

    # Cross-system conflicts at warning level can be degraded
    if conflict.conflict_type == ConflictType.CROSS_SYSTEM:
        return True

    # Version mismatch at warning level can be degraded
    if conflict.conflict_type == ConflictType.VERSION_MISMATCH:
        return True

    # Info level conflicts can always be degraded
    if conflict.severity == "info":
        return True

    return False


def resolve_conflict_strategy(
    conflicts: List[ConflictDetectionResult],
    *,
    auto_resolve_config: Optional[Dict[str, Any]] = None,
) -> ConflictResolutionStrategy:
    """Determine the resolution strategy for a set of conflicts.

    Args:
        conflicts: List of detected conflicts
        auto_resolve_config: Optional configuration for auto-resolution

    Returns:
        Resolution strategy: REJECT, DEGRADE, or OVERRIDE
    """
    if not conflicts:
        return ConflictResolutionStrategy.REJECT  # No conflicts, proceed normally

    # Check if any critical blocking conflict exists
    has_critical = any(c.is_blocking for c in conflicts)

    if has_critical:
        return ConflictResolutionStrategy.REJECT

    # Check if degradation is enabled in config
    if auto_resolve_config:
        allow_degrade = auto_resolve_config.get("allow_degrade", False)
        if allow_degrade:
            # Check if all conflicts can be degraded
            if all(should_degrade(c) for c in conflicts):
                return ConflictResolutionStrategy.DEGRADE

    # Default to REJECT for safety
    return ConflictResolutionStrategy.REJECT


def merge_degraded_results(results: List[DegradedResult]) -> DegradedResult:
    """Merge multiple degraded results into a single summary.

    Useful when aggregating across multiple entities with conflicts.

    Args:
        results: List of degraded results to merge

    Returns:
        Merged degraded result
    """
    if not results:
        raise ValueError("Cannot merge empty list of degraded results")

    if len(results) == 1:
        return results[0]

    # Use first result as base
    base = results[0]

    # Collect all available sources
    all_sources: List[Dict[str, Any]] = []
    for r in results:
        all_sources.extend(r.available_sources)

    # Build merged summary
    conflict_types = list({r.conflict_type.value for r in results})
    summary = (
        f"Multiple mapping conflicts detected ({len(results)} entities affected). "
        f"Conflict types: {', '.join(conflict_types)}. "
        f"All available sources are shown separately without aggregation."
    )

    return DegradedResult(
        unified_id=base.unified_id,  # Primary entity
        entity_type=base.entity_type,
        conflict_type=base.conflict_type,  # Primary conflict type
        available_sources=all_sources,
        conflict_summary=summary,
        recommended_action="Review all listed conflicts and resolve before aggregation. Contact data steward if needed.",
        requires_manual_review=True,
        detected_at=datetime.now(timezone.utc),
        request_id=base.request_id,
    )
