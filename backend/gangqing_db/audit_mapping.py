"""Audit event models and utilities for semantic layer mapping operations.

This module provides mapping-specific audit event definitions and logging utilities
for the semantic layer entity mapping system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from gangqing.common.context import RequestContext
    from gangqing.semantic.models import EntityType


class MappingAuditEventType(str, Enum):
    """Audit event types for mapping operations."""

    MAPPING_QUERY = "mapping.query"
    """Mapping query operation."""

    MAPPING_CONFLICT_DETECTED = "mapping.conflict_detected"
    """Conflict detected during mapping operation."""

    MAPPING_AGGREGATION_BLOCKED = "mapping.aggregation_blocked"
    """Aggregation blocked by gate."""

    MAPPING_VERSION_CREATED = "mapping.version_created"
    """New mapping version created."""

    MAPPING_VERSION_UPDATED = "mapping.version_updated"
    """Mapping version updated."""

    MAPPING_VERSION_DELETED = "mapping.version_deleted"
    """Mapping version deleted (soft delete)."""


class AuditMappingEvent(BaseModel):
    """Audit event model for semantic mapping operations.

    Records all mapping-related events for audit and compliance:
    - mapping.query: Mapping queries (fields: unified_id, entity_type, version, result_count)
    - mapping.conflict_detected: Conflict detection (fields: conflict_type, unified_id, details)
    - mapping.aggregation_blocked: Gate blocking (fields: reason, entity_refs)
    - mapping.version_created/updated/deleted: Version lifecycle changes
    """

    event_type: str = Field(min_length=1, description="Event type")
    unified_id: str = Field(description="Unified entity ID")
    entity_type: str = Field(description="Entity type (equipment/material/batch/order)")
    version: Optional[int] = Field(default=None, description="Version number")
    tenant_id: str = Field(description="Tenant ID")
    project_id: str = Field(description="Project ID")
    user_id: Optional[str] = Field(default=None, description="User ID who performed the action")
    request_id: str = Field(description="Request ID for tracing")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp"
    )
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional event details")

    # Extended fields for T56.4
    result_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Number of results (for query events)",
    )
    conflict_type: Optional[str] = Field(
        default=None,
        description="Type of conflict detected",
    )
    severity: Optional[Literal["critical", "warning", "info"]] = Field(
        default=None,
        description="Conflict severity level",
    )
    block_reason: Optional[str] = Field(
        default=None,
        description="Reason for aggregation block",
    )
    entity_refs: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Entity references involved in gate check",
    )
    result_status: Literal["success", "failure", "blocked", "detected"] = Field(
        default="success",
        description="Operation result status",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Error code (if failure/blocked)",
    )

    model_config = {"populate_by_name": True}

    @field_validator("block_reason")
    @classmethod
    def validate_block_reason_english(cls, v: Optional[str]) -> Optional[str]:
        """Ensure block reason is in English."""
        if v is None:
            return v
        if any(ord(c) > 127 for c in v):
            raise ValueError("Block reason must be in English")
        return v


def build_mapping_audit_event(
    event_type: str,
    unified_id: str,
    entity_type: Any,
    ctx: Any,
    version: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditMappingEvent:
    """Build an AuditMappingEvent from request context.

    Args:
        event_type: Event type (e.g., mapping.create, mapping.update)
        unified_id: Unified entity ID
        entity_type: Entity type
        ctx: RequestContext with tenant/project/user info
        version: Optional version number
        details: Optional additional details

    Returns:
        AuditMappingEvent instance
    """
    entity_type_value = entity_type.value if hasattr(entity_type, "value") else str(entity_type)
    return AuditMappingEvent(
        event_type=event_type,
        unified_id=unified_id,
        entity_type=entity_type_value,
        version=version,
        tenant_id=ctx.tenant_id,
        project_id=ctx.project_id,
        user_id=getattr(ctx, "user_id", None),
        request_id=ctx.request_id,
        details=details,
    )


class AuditMappingLogger:
    """Logger for mapping audit events.

    Provides methods to log different types of mapping events:
    - Query events
    - Conflict detection events
    - Gate blocking events
    - Version lifecycle events
    """

    def __init__(self, ctx: Any, audit_log_fn: Any = None) -> None:
        """Initialize logger with context and audit function.

        Args:
            ctx: RequestContext with tenant_id, project_id, request_id
            audit_log_fn: Function to insert audit log (e.g., insert_audit_log_event)
        """
        self.ctx = ctx
        self._audit_log_fn = audit_log_fn

    def _base_event(self, event_type: MappingAuditEventType) -> AuditMappingEvent:
        """Create base audit event with context fields."""
        return AuditMappingEvent(
            event_type=event_type.value,
            unified_id="",
            entity_type="",
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            user_id=getattr(self.ctx, "user_id", None),
            request_id=self.ctx.request_id,
        )

    def log_mapping_query(
        self,
        unified_id: str,
        entity_type: str,
        *,
        version: Optional[int] = None,
        result_count: int = 0,
        found: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditMappingEvent:
        """Log a mapping query event."""
        event = self._base_event(MappingAuditEventType.MAPPING_QUERY)
        event.unified_id = unified_id
        event.entity_type = entity_type
        event.version = version
        event.result_count = result_count
        event.result_status = "success" if found else "failure"
        event.details = {**(details or {}), "found": found}
        if not found:
            event.error_code = "NOT_FOUND"

        self._insert_event(event)
        return event

    def log_conflict_detected(
        self,
        unified_id: str,
        entity_type: str,
        conflict_type: str,
        *,
        severity: Literal["critical", "warning", "info"] = "critical",
        conflict_details: Optional[Dict[str, Any]] = None,
    ) -> AuditMappingEvent:
        """Log a conflict detection event."""
        event = self._base_event(MappingAuditEventType.MAPPING_CONFLICT_DETECTED)
        event.unified_id = unified_id
        event.entity_type = entity_type
        event.conflict_type = conflict_type
        event.severity = severity
        event.result_status = "detected"
        event.details = conflict_details

        self._insert_event(event)
        return event

    def log_aggregation_blocked(
        self,
        reason: str,
        *,
        unified_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_refs: Optional[List[Dict[str, Any]]] = None,
        conflict_count: int = 0,
        conflict_types: Optional[List[str]] = None,
        error_code: str = "AGGREGATION_BLOCKED",
    ) -> AuditMappingEvent:
        """Log an aggregation blocked event."""
        event = self._base_event(MappingAuditEventType.MAPPING_AGGREGATION_BLOCKED)
        event.unified_id = unified_id or ""
        event.entity_type = entity_type or ""
        event.block_reason = reason
        event.entity_refs = entity_refs
        event.result_status = "blocked"
        event.error_code = error_code
        event.details = {
            "conflict_count": conflict_count,
            "conflict_types": conflict_types or [],
        }

        self._insert_event(event)
        return event

    def log_version_created(
        self,
        unified_id: str,
        entity_type: str,
        version: int,
        *,
        source_system: str,
        source_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditMappingEvent:
        """Log a mapping version created event."""
        event = self._base_event(MappingAuditEventType.MAPPING_VERSION_CREATED)
        event.unified_id = unified_id
        event.entity_type = entity_type
        event.version = version
        event.result_status = "success"
        event.details = {
            **(details or {}),
            "source_system": source_system,
            "source_id": source_id,
        }

        self._insert_event(event)
        return event

    def log_version_updated(
        self,
        unified_id: str,
        entity_type: str,
        new_version: int,
        old_version: int,
        *,
        source_system_changed: bool = False,
        source_id_changed: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditMappingEvent:
        """Log a mapping version updated event."""
        event = self._base_event(MappingAuditEventType.MAPPING_VERSION_UPDATED)
        event.unified_id = unified_id
        event.entity_type = entity_type
        event.version = new_version
        event.result_status = "success"
        event.details = {
            **(details or {}),
            "old_version": old_version,
            "new_version": new_version,
            "source_system_changed": source_system_changed,
            "source_id_changed": source_id_changed,
        }

        self._insert_event(event)
        return event

    def log_version_deleted(
        self,
        unified_id: str,
        entity_type: str,
        version: int,
        *,
        soft_delete: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditMappingEvent:
        """Log a mapping version deleted event."""
        event = self._base_event(MappingAuditEventType.MAPPING_VERSION_DELETED)
        event.unified_id = unified_id
        event.entity_type = entity_type
        event.version = version
        event.result_status = "success"
        event.details = {
            **(details or {}),
            "soft_delete": soft_delete,
        }

        self._insert_event(event)
        return event

    def _insert_event(self, event: AuditMappingEvent) -> None:
        """Insert event into audit log."""
        if self._audit_log_fn is None:
            return

        try:
            from gangqing_db.audit_log import AuditLogEvent, insert_audit_log_event

            audit_event = AuditLogEvent(
                eventType=event.event_type,
                timestamp=event.timestamp,
                requestId=event.request_id,
                tenantId=event.tenant_id,
                projectId=event.project_id,
                sessionId=None,
                userId=event.user_id,
                actionSummary=event.model_dump(
                    include={
                        "unified_id",
                        "entity_type",
                        "version",
                        "result_count",
                        "conflict_type",
                        "severity",
                        "block_reason",
                        "entity_refs",
                        "details",
                    },
                    exclude_none=True,
                ),
                result_status=event.result_status,
                error_code=event.error_code,
            )

            insert_audit_log_event(audit_event, ctx=self.ctx)
        except Exception:
            pass


def create_audit_mapping_logger(
    ctx: Any,
    audit_log_fn: Any = None,
) -> AuditMappingLogger:
    """Factory function to create an AuditMappingLogger.

    Args:
        ctx: RequestContext with tenant_id, project_id, request_id
        audit_log_fn: Function to insert audit log (e.g., insert_audit_log_event)

    Returns:
        AuditMappingLogger instance
    """
    return AuditMappingLogger(ctx, audit_log_fn)
