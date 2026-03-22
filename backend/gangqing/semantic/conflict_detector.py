"""Core conflict detection module for entity ID mapping.

This module provides the ConflictDetector class that detects various types
of mapping conflicts including multi-to-one mappings, cross-system conflicts,
missing mappings, and version mismatches.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from gangqing.semantic.models.conflict_detection import (
    ConflictAuditEvent,
    ConflictDetectionResult,
    ConflictResolutionStrategy,
    ConflictType,
)
from gangqing.semantic.models.entity_mapping import (
    EntityMappingResponse,
    EntityType,
    MAPPING_READ_CAPABILITY,
)


class ConflictDetector:
    """Detector for entity mapping conflicts.

    Provides methods to detect conflicts at various levels:
    - By unified_id: Detect conflicts for a specific unified entity
    - By source_id: Reverse lookup conflicts from source system perspective
    - Multi-to-one scanning: Detect all multi-to-one conflicts in a scope
    - Consistency validation: Validate mapping consistency before aggregation
    """

    def __init__(
        self,
        *,
        mapping_version_manager: Any,  # MappingVersionManager instance
        audit_logger: Optional[Any] = None,  # Optional audit logger
    ) -> None:
        """Initialize the conflict detector.

        Args:
            mapping_version_manager: Instance of MappingVersionManager for DB queries
            audit_logger: Optional audit logger for conflict detection events
        """
        self._manager = mapping_version_manager
        self._audit_logger = audit_logger

    def detect_by_unified_id(
        self,
        unified_id: str,
        entity_type: EntityType,
        *,
        tenant_id: str,
        project_id: str,
        request_id: Optional[str] = None,
    ) -> List[ConflictDetectionResult]:
        """Detect conflicts for a specific unified entity ID.

        Checks for:
        - Multi-to-one mappings (same unified_id -> multiple source_ids)
        - Missing mappings (no mapping exists)

        Args:
            unified_id: Unified entity ID to check
            entity_type: Entity type
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation
            request_id: Optional request ID for tracing

        Returns:
            List of detected conflicts (empty if no conflicts)
        """
        conflicts: List[ConflictDetectionResult] = []

        # Query all mappings for this unified_id
        mappings = self._manager.get_all_mappings_for_unified_id(
            unified_id=unified_id,
            entity_type=entity_type,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        # Check for missing mapping
        if not mappings:
            conflict = ConflictDetectionResult(
                unified_id=unified_id,
                entity_type=entity_type,
                conflict_type=ConflictType.MAPPING_MISSING,
                conflict_details={
                    "reason": "No mapping exists for this unified_id",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                },
                severity="critical",
                request_id=request_id,
            )
            conflicts.append(conflict)
            self._log_conflict_detected(conflict, tenant_id, project_id, request_id)
            return conflicts

        # Check for multi-to-one conflict (multiple source_ids)
        if len(mappings) > 1:
            source_systems = list({m.source_system for m in mappings})
            source_ids = [m.source_id for m in mappings]

            # Only report as conflict if different source systems
            if len(source_systems) > 1:
                conflict = ConflictDetectionResult(
                    unified_id=unified_id,
                    entity_type=entity_type,
                    conflict_type=ConflictType.MULTI_TO_ONE,
                    conflict_details={
                        "mapping_count": len(mappings),
                        "source_systems": source_systems,
                        "source_ids": source_ids,
                        "versions": [m.version for m in mappings],
                    },
                    severity="critical",
                    request_id=request_id,
                )
                conflicts.append(conflict)
                self._log_conflict_detected(conflict, tenant_id, project_id, request_id)
            else:
                # Same system, multiple IDs - warning level
                conflict = ConflictDetectionResult(
                    unified_id=unified_id,
                    entity_type=entity_type,
                    conflict_type=ConflictType.CROSS_SYSTEM,
                    conflict_details={
                        "mapping_count": len(mappings),
                        "source_system": source_systems[0],
                        "source_ids": source_ids,
                        "note": "Multiple source_ids in same system",
                    },
                    severity="warning",
                    request_id=request_id,
                )
                conflicts.append(conflict)
                self._log_conflict_detected(conflict, tenant_id, project_id, request_id)

        return conflicts

    def detect_by_source_id(
        self,
        source_system: str,
        source_id: str,
        *,
        tenant_id: str,
        project_id: str,
        request_id: Optional[str] = None,
    ) -> List[ConflictDetectionResult]:
        """Detect conflicts by looking up from source system perspective.

        Useful for detecting cases where a source system ID maps to
        multiple unified IDs (indicating data quality issues).

        Args:
            source_system: Source system name (ERP/MES/DCS/EAM)
            source_id: Source system original ID
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation
            request_id: Optional request ID for tracing

        Returns:
            List of detected conflicts
        """
        conflicts: List[ConflictDetectionResult] = []

        # Query all mappings for this source_id
        mappings = self._manager.get_mappings_by_source_id(
            source_system=source_system,
            source_id=source_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        if len(mappings) > 1:
            unified_ids = list({m.unified_id for m in mappings})
            entity_types = list({m.entity_type for m in mappings})

            conflict = ConflictDetectionResult(
                unified_id=",".join(unified_ids),  # Composite indicator
                entity_type=entity_types[0] if len(entity_types) == 1 else EntityType.EQUIPMENT,
                conflict_type=ConflictType.CROSS_SYSTEM,
                conflict_details={
                    "source_system": source_system,
                    "source_id": source_id,
                    "unified_ids": unified_ids,
                    "entity_types": [et.value for et in entity_types],
                    "mapping_count": len(mappings),
                    "reason": "Source ID maps to multiple unified IDs",
                },
                severity="warning",
                request_id=request_id,
            )
            conflicts.append(conflict)
            self._log_conflict_detected(conflict, tenant_id, project_id, request_id)

        return conflicts

    def detect_multi_to_one(
        self,
        tenant_id: str,
        project_id: str,
        *,
        entity_type: Optional[EntityType] = None,
        request_id: Optional[str] = None,
    ) -> List[ConflictDetectionResult]:
        """Scan and detect all multi-to-one conflicts in a tenant/project scope.

        This is an expensive operation that should be run periodically
        or during data quality audits.

        Args:
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation
            entity_type: Optional filter by entity type
            request_id: Optional request ID for tracing

        Returns:
            List of all multi-to-one conflicts detected
        """
        conflicts: List[ConflictDetectionResult] = []

        # Get all unified_ids that have multiple mappings
        multi_mappings = self._manager.get_unified_ids_with_multiple_mappings(
            tenant_id=tenant_id,
            project_id=project_id,
            entity_type=entity_type,
        )

        for unified_id, mappings in multi_mappings.items():
            # Determine entity type from mappings
            detected_entity_type = entity_type or mappings[0].entity_type

            # Check if different source systems
            source_systems = list({m.source_system for m in mappings})

            if len(source_systems) > 1:
                conflict = ConflictDetectionResult(
                    unified_id=unified_id,
                    entity_type=detected_entity_type,
                    conflict_type=ConflictType.MULTI_TO_ONE,
                    conflict_details={
                        "mapping_count": len(mappings),
                        "source_systems": source_systems,
                        "source_ids": [m.source_id for m in mappings],
                    },
                    severity="critical",
                    request_id=request_id,
                )
                conflicts.append(conflict)
                self._log_conflict_detected(conflict, tenant_id, project_id, request_id)

        return conflicts

    def validate_mapping_consistency(
        self,
        mappings: List[EntityMappingResponse],
        *,
        tenant_id: str,
        project_id: str,
        request_id: Optional[str] = None,
    ) -> Optional[ConflictDetectionResult]:
        """Validate a set of mappings for consistency before aggregation.

        This method is called before cross-system aggregation to ensure
        all required mappings are consistent and valid.

        Args:
            mappings: List of mappings to validate
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation
            request_id: Optional request ID for tracing

        Returns:
            ConflictDetectionResult if inconsistency found, None otherwise
        """
        if not mappings:
            return None

        # Group by unified_id to check for conflicts within the set
        by_unified_id: Dict[str, List[EntityMappingResponse]] = {}
        for m in mappings:
            if m.unified_id not in by_unified_id:
                by_unified_id[m.unified_id] = []
            by_unified_id[m.unified_id].append(m)

        # Check each group for conflicts
        for unified_id, group in by_unified_id.items():
            if len(group) > 1:
                source_systems = list({m.source_system for m in group})

                if len(source_systems) > 1:
                    conflict = ConflictDetectionResult(
                        unified_id=unified_id,
                        entity_type=group[0].entity_type,
                        conflict_type=ConflictType.MULTI_TO_ONE,
                        conflict_details={
                            "validation_context": "pre_aggregation",
                            "mapping_count": len(group),
                            "source_systems": source_systems,
                            "source_ids": [m.source_id for m in group],
                        },
                        severity="critical",
                        request_id=request_id,
                    )
                    self._log_conflict_detected(conflict, tenant_id, project_id, request_id)
                    return conflict

        return None

    def check_aggregation_blocked(
        self,
        unified_ids: List[str],
        entity_type: EntityType,
        *,
        tenant_id: str,
        project_id: str,
        request_id: Optional[str] = None,
    ) -> Tuple[bool, List[ConflictDetectionResult]]:
        """Check if aggregation should be blocked due to conflicts.

        This is the main entry point for aggregation gate checking.

        Args:
            unified_ids: List of unified IDs to be aggregated
            entity_type: Entity type
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation
            request_id: Optional request ID for tracing

        Returns:
            Tuple of (is_blocked, list_of_conflicts)
        """
        all_conflicts: List[ConflictDetectionResult] = []

        for unified_id in unified_ids:
            conflicts = self.detect_by_unified_id(
                unified_id=unified_id,
                entity_type=entity_type,
                tenant_id=tenant_id,
                project_id=project_id,
                request_id=request_id,
            )
            all_conflicts.extend(conflicts)

        # Aggregation is blocked if any critical conflict exists
        is_blocked = any(c.is_blocking for c in all_conflicts)

        if is_blocked and self._audit_logger:
            self._log_aggregation_blocked(
                unified_ids=unified_ids,
                entity_type=entity_type,
                conflicts=all_conflicts,
                tenant_id=tenant_id,
                project_id=project_id,
                request_id=request_id,
            )

        return is_blocked, all_conflicts

    def _log_conflict_detected(
        self,
        conflict: ConflictDetectionResult,
        tenant_id: str,
        project_id: str,
        request_id: Optional[str],
    ) -> None:
        """Log conflict detection to audit log."""
        if not self._audit_logger:
            return

        audit_event = ConflictAuditEvent(
            event_type="mapping.conflict_detected",
            unified_id=conflict.unified_id,
            entity_type=conflict.entity_type,
            conflict_type=conflict.conflict_type,
            severity=conflict.severity,
            tenant_id=tenant_id,
            project_id=project_id,
            request_id=request_id or conflict.request_id or "unknown",
            details=conflict.conflict_details,
        )

        self._audit_logger.log_mapping_event(audit_event)

    def _log_aggregation_blocked(
        self,
        unified_ids: List[str],
        entity_type: EntityType,
        conflicts: List[ConflictDetectionResult],
        tenant_id: str,
        project_id: str,
        request_id: Optional[str],
    ) -> None:
        """Log aggregation blocked event to audit log."""
        if not self._audit_logger:
            return

        # Use first conflict's unified_id as primary
        primary_conflict = conflicts[0] if conflicts else None

        audit_event = ConflictAuditEvent(
            event_type="mapping.aggregation_blocked",
            unified_id=primary_conflict.unified_id if primary_conflict else unified_ids[0],
            entity_type=entity_type,
            conflict_type=primary_conflict.conflict_type if primary_conflict else ConflictType.MAPPING_MISSING,
            severity="critical",
            resolution_strategy=ConflictResolutionStrategy.REJECT,
            tenant_id=tenant_id,
            project_id=project_id,
            request_id=request_id or "unknown",
            details={
                "unified_ids": unified_ids,
                "conflict_count": len(conflicts),
                "conflict_types": [c.conflict_type.value for c in conflicts],
                "reason": "Aggregation blocked due to mapping conflicts",
            },
        )

        self._audit_logger.log_mapping_event(audit_event)
