"""Aggregation gate module for cross-system data aggregation.

This module provides the AggregationGate class that enforces mandatory
mapping consistency checks before allowing cross-system data aggregation.
Any mapping conflicts or missing mappings result in immediate blocking
with AGGREGATION_BLOCKED error.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

import structlog

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.semantic.conflict_detector import ConflictDetector
from gangqing.semantic.models import (
    ConflictAuditEvent,
    ConflictDetectionResult,
    ConflictResolutionStrategy,
    ConflictType,
    EntityMappingResponse,
    EntityType,
)


logger = structlog.get_logger(__name__)


class EntityRef:
    """Reference to an entity for aggregation gate checking.

    Represents a unified entity that needs to be verified before
    cross-system aggregation is allowed.
    """

    def __init__(
        self,
        unified_id: str,
        entity_type: EntityType,
        required_source_systems: Optional[List[str]] = None,
    ) -> None:
        """Initialize entity reference.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type (equipment, material, batch, order)
            required_source_systems: Optional list of required source systems
                                    (e.g., ["ERP", "MES", "DCS"])
        """
        self.unified_id = unified_id
        self.entity_type = entity_type
        self.required_source_systems = required_source_systems or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "unified_id": self.unified_id,
            "entity_type": self.entity_type.value,
            "required_source_systems": self.required_source_systems,
        }


class AggregationGateResult:
    """Result of aggregation gate check.

    Indicates whether aggregation is allowed or blocked,
    with detailed conflict information if blocked.
    """

    def __init__(
        self,
        allowed: bool,
        blocked_reason: Optional[str] = None,
        conflicts: Optional[List[ConflictDetectionResult]] = None,
        entity_refs: Optional[List[EntityRef]] = None,
    ) -> None:
        """Initialize gate result.

        Args:
            allowed: Whether aggregation is allowed
            blocked_reason: Reason for blocking (if blocked)
            conflicts: List of detected conflicts (if any)
            entity_refs: Entity references that were checked
        """
        self.allowed = allowed
        self.blocked_reason = blocked_reason
        self.conflicts = conflicts or []
        self.entity_refs = entity_refs or []
        self.checked_at = datetime.now(timezone.utc)

    @property
    def is_blocked(self) -> bool:
        """Check if aggregation is blocked."""
        return not self.allowed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "allowed": self.allowed,
            "blocked_reason": self.blocked_reason,
            "checked_at": self.checked_at.isoformat(),
            "conflict_count": len(self.conflicts),
            "conflicts": [
                {
                    "unified_id": c.unified_id,
                    "entity_type": c.entity_type.value,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity,
                }
                for c in self.conflicts
            ],
            "entity_refs": [ref.to_dict() for ref in self.entity_refs],
        }


class AggregationBlockedError(AppError):
    """Error raised when aggregation is blocked by the gate.

    This error uses AGGREGATION_BLOCKED code and includes
    structured details about the conflicts that caused blocking.
    """

    def __init__(
        self,
        entity_refs: List[EntityRef],
        conflicts: List[ConflictDetectionResult],
        *,
        request_id: str,
        tenant_id: str,
        project_id: str,
    ) -> None:
        """Initialize aggregation blocked error.

        Args:
            entity_refs: Entity references that were being aggregated
            conflicts: Conflicts that caused the block
            request_id: Request ID for tracing
            tenant_id: Tenant ID
            project_id: Project ID
        """
        conflict_types = list({c.conflict_type.value for c in conflicts})

        message = (
            f"Aggregation blocked due to mapping inconsistency: "
            f"missing or conflicting unified_id mappings for "
            f"{len(entity_refs)} entity(s). "
            f"Conflicts: {', '.join(conflict_types)}. "
            f"Resolve conflicts before retry."
        )

        details: Dict[str, Any] = {
            "entity_refs": [ref.to_dict() for ref in entity_refs],
            "conflict_count": len(conflicts),
            "conflict_types": conflict_types,
            "conflicts": [
                {
                    "unified_id": c.unified_id,
                    "entity_type": c.entity_type.value,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity,
                    "conflict_details": c.conflict_details,
                }
                for c in conflicts
            ],
            "tenant_id": tenant_id,
            "project_id": project_id,
        }

        super().__init__(
            code=ErrorCode.AGGREGATION_BLOCKED,
            message=message,
            request_id=request_id,
            details=details,
            retryable=False,  # Mapping conflicts are not retryable
        )
        self.entity_refs = entity_refs
        self.conflicts = conflicts


class MappingVersionManagerProtocol(Protocol):
    """Protocol for mapping version manager interface.

    This protocol defines the interface expected by AggregationGate,
    allowing for dependency injection and testability.
    """

    def get_all_mappings_for_unified_id(
        self,
        unified_id: str,
        entity_type: EntityType,
        tenant_id: str,
        project_id: str,
    ) -> List[EntityMappingResponse]: ...

    def get_mappings_by_source_id(
        self,
        source_system: str,
        source_id: str,
        tenant_id: str,
        project_id: str,
    ) -> List[EntityMappingResponse]: ...

    def get_unified_ids_with_multiple_mappings(
        self,
        tenant_id: str,
        project_id: str,
        entity_type: Optional[EntityType] = None,
    ) -> Dict[str, List[EntityMappingResponse]]: ...


class AggregationGate:
    """Gate for cross-system data aggregation.

    Enforces mandatory mapping consistency checks before allowing
    cross-system aggregation. Any mapping conflicts or missing
    mappings result in immediate blocking with structured error.

    Usage:
        gate = AggregationGate(ctx, mapping_manager)
        result = gate.check_aggregation_prerequisites(entity_refs)
        if not result.allowed:
            raise AggregationBlockedError(...)
    """

    def __init__(
        self,
        ctx: RequestContext,
        mapping_manager: MappingVersionManagerProtocol,
    ) -> None:
        """Initialize aggregation gate.

        Args:
            ctx: RequestContext with tenant_id, project_id, request_id
            mapping_manager: Manager for mapping queries
        """
        self.ctx = ctx
        self._mapping_manager = mapping_manager
        self._conflict_detector = ConflictDetector(
            mapping_version_manager=mapping_manager,
            audit_logger=self,
        )

    def check_aggregation_prerequisites(
        self,
        entity_refs: List[EntityRef],
    ) -> AggregationGateResult:
        """Check prerequisites for cross-system aggregation.

        This is the main entry point for aggregation gate checking.
        It verifies:
        1. All entity_refs have valid mappings
        2. No multi-to-one conflicts exist
        3. All required source systems are present

        Args:
            entity_refs: List of entity references to be aggregated

        Returns:
            AggregationGateResult indicating allow/block status
        """
        if not entity_refs:
            # Empty aggregation is always allowed
            return AggregationGateResult(allowed=True, entity_refs=[])

        all_conflicts: List[ConflictDetectionResult] = []

        # Check each entity_ref for conflicts
        for ref in entity_refs:
            conflicts = self._conflict_detector.detect_by_unified_id(
                unified_id=ref.unified_id,
                entity_type=ref.entity_type,
                tenant_id=self.ctx.tenant_id,
                project_id=self.ctx.project_id,
                request_id=self.ctx.request_id,
            )

            # Filter for blocking conflicts only
            blocking_conflicts = [c for c in conflicts if c.is_blocking]
            all_conflicts.extend(blocking_conflicts)

            # Check required source systems if specified
            if ref.required_source_systems and not conflicts:
                missing_systems = self._check_required_source_systems(ref)
                if missing_systems:
                    # Create synthetic conflict for missing source system
                    conflict = ConflictDetectionResult(
                        unified_id=ref.unified_id,
                        entity_type=ref.entity_type,
                        conflict_type=ConflictType.MAPPING_MISSING,
                        conflict_details={
                            "reason": "Required source system not present",
                            "missing_systems": missing_systems,
                            "required_systems": ref.required_source_systems,
                        },
                        severity="critical",
                        request_id=self.ctx.request_id,
                    )
                    all_conflicts.append(conflict)

        # Determine if aggregation is blocked
        is_blocked = len(all_conflicts) > 0

        if is_blocked:
            self._log_aggregation_blocked(entity_refs, all_conflicts)

            return AggregationGateResult(
                allowed=False,
                blocked_reason="Aggregation blocked due to mapping conflicts",
                conflicts=all_conflicts,
                entity_refs=entity_refs,
            )

        return AggregationGateResult(
            allowed=True,
            entity_refs=entity_refs,
        )

    def check_single_entity(
        self,
        unified_id: str,
        entity_type: EntityType,
        required_source_systems: Optional[List[str]] = None,
    ) -> AggregationGateResult:
        """Check aggregation prerequisites for a single entity.

        Convenience method for checking a single entity.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type
            required_source_systems: Optional required source systems

        Returns:
            AggregationGateResult
        """
        ref = EntityRef(
            unified_id=unified_id,
            entity_type=entity_type,
            required_source_systems=required_source_systems,
        )
        return self.check_aggregation_prerequisites([ref])

    def _check_required_source_systems(
        self,
        ref: EntityRef,
    ) -> List[str]:
        """Check if all required source systems are present.

        Args:
            ref: Entity reference with required systems

        Returns:
            List of missing source systems (empty if all present)
        """
        if not ref.required_source_systems:
            return []

        # Get current mappings
        mappings = self._mapping_manager.get_all_mappings_for_unified_id(
            unified_id=ref.unified_id,
            entity_type=ref.entity_type,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
        )

        present_systems = {m.source_system for m in mappings}
        missing = [
            sys for sys in ref.required_source_systems
            if sys not in present_systems
        ]

        return missing

    def _log_aggregation_blocked(
        self,
        entity_refs: List[EntityRef],
        conflicts: List[ConflictDetectionResult],
    ) -> None:
        """Log aggregation blocked event to audit."""
        audit_event = ConflictAuditEvent(
            event_type="mapping.aggregation_blocked",
            unified_id=entity_refs[0].unified_id if entity_refs else "unknown",
            entity_type=entity_refs[0].entity_type if entity_refs else EntityType.EQUIPMENT,
            conflict_type=conflicts[0].conflict_type if conflicts else ConflictType.MAPPING_MISSING,
            severity="critical",
            resolution_strategy=ConflictResolutionStrategy.REJECT,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            user_id=self.ctx.user_id,
            request_id=self.ctx.request_id,
            details={
                "entity_count": len(entity_refs),
                "conflict_count": len(conflicts),
                "conflict_types": list({c.conflict_type.value for c in conflicts}),
                "entity_refs": [ref.to_dict() for ref in entity_refs],
            },
        )

        write_audit_event(
            ctx=self.ctx,
            event_type=AuditEventType.MAPPING_AGGREGATION_BLOCKED,
            resource="semantic:aggregation:gate",
            action_summary={
                "entity_count": len(entity_refs),
                "conflict_count": len(conflicts),
                "conflict_types": list({c.conflict_type.value for c in conflicts}),
            },
            result_status="blocked",
            error_code=ErrorCode.AGGREGATION_BLOCKED.value,
        )

        logger.warning(
            "aggregation_blocked",
            entity_count=len(entity_refs),
            conflict_count=len(conflicts),
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            request_id=self.ctx.request_id,
        )

    # Audit logger interface for ConflictDetector
    def log_mapping_event(self, audit_event: ConflictAuditEvent) -> None:
        """Log mapping event from ConflictDetector to audit."""
        event_type_map = {
            "mapping.conflict_detected": AuditEventType.MAPPING_CONFLICT_DETECTED,
            "mapping.conflict_resolved": AuditEventType.MAPPING_CONFLICT_RESOLVED,
            "mapping.aggregation_blocked": AuditEventType.MAPPING_AGGREGATION_BLOCKED,
        }

        audit_type = event_type_map.get(
            audit_event.event_type,
            AuditEventType.MAPPING_CONFLICT_DETECTED,
        )

        write_audit_event(
            ctx=self.ctx,
            event_type=audit_type,
            resource=f"semantic:mapping:{audit_event.entity_type.value}:{audit_event.unified_id}",
            action_summary={
                "conflict_type": audit_event.conflict_type.value,
                "severity": audit_event.severity,
                "resolution": audit_event.resolution_strategy.value if audit_event.resolution_strategy else None,
            },
            result_status="detected" if audit_event.event_type == "mapping.conflict_detected" else "blocked",
        )


def create_aggregation_gate(
    ctx: RequestContext,
    mapping_manager: MappingVersionManagerProtocol,
) -> AggregationGate:
    """Factory function to create aggregation gate.

    Args:
        ctx: RequestContext
        mapping_manager: Mapping version manager

    Returns:
        Configured AggregationGate instance
    """
    return AggregationGate(ctx, mapping_manager)
