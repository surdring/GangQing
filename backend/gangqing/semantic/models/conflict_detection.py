"""Semantic layer models for conflict detection and resolution.

This module defines the Pydantic schemas for mapping conflict detection,
including conflict types, detection results, and resolution strategies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from gangqing.semantic.models.entity_mapping import EntityType


class ConflictType(str, Enum):
    """Types of mapping conflicts detected in the unified ID system."""

    MULTI_TO_ONE = "multi_to_one"
    """Same unified_id maps to multiple source_ids across different systems."""

    CROSS_SYSTEM = "cross_system"
    """ID conflict across different source systems."""

    MAPPING_MISSING = "mapping_missing"
    """Required mapping does not exist."""

    VERSION_MISMATCH = "version_mismatch"
    """Version mismatch between expected and actual."""


class ConflictResolutionStrategy(str, Enum):
    """Strategies for resolving detected conflicts."""

    REJECT = "reject"
    """Reject the operation and return error."""

    DEGRADE = "degrade"
    """Degrade to showing available data sources without aggregation."""

    OVERRIDE = "override"
    """Override with explicit user authorization (requires audit trail)."""


class ConflictDetectionResult(BaseModel):
    """Result model for conflict detection.

    Represents a single detected conflict with details about the conflict
    type, severity, and context for downstream handling.
    """

    unified_id: str = Field(min_length=1, description="Unified entity ID involved in conflict")
    entity_type: EntityType = Field(description="Entity type")
    conflict_type: ConflictType = Field(description="Type of conflict detected")
    conflict_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed conflict information (e.g., conflicting source systems)",
    )
    severity: Literal["critical", "warning", "info"] = Field(
        description="Severity level of the conflict"
    )
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when conflict was detected"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request ID for tracing"
    )

    model_config = {"populate_by_name": True}

    @property
    def is_blocking(self) -> bool:
        """Check if this conflict should block aggregation operations."""
        return self.severity == "critical" or self.conflict_type in (
            ConflictType.MULTI_TO_ONE,
            ConflictType.MAPPING_MISSING,
        )


class DegradedResult(BaseModel):
    """Result model for degraded response when conflict is detected.

    Instead of returning aggregated data, this model provides:
    - Available data sources without aggregation
    - Conflict explanation for human review
    - Recommended actions
    """

    unified_id: str = Field(description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    conflict_type: ConflictType = Field(description="Type of conflict detected")
    available_sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of available data sources (without aggregation)"
    )
    conflict_summary: str = Field(
        description="Human-readable summary of the conflict"
    )
    recommended_action: str = Field(
        description="Recommended action for resolving the conflict"
    )
    requires_manual_review: bool = Field(
        default=True,
        description="Whether manual review is required"
    )
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Detection timestamp"
    )
    request_id: Optional[str] = Field(
        default=None,
        alias="requestId",
        description="Request ID for tracing"
    )

    model_config = {"populate_by_name": True}


class ConflictAuditEvent(BaseModel):
    """Audit event model for conflict detection operations.

    Records when conflicts are detected, handled, and resolved.
    """

    event_type: Literal[
        "mapping.conflict_detected",
        "mapping.conflict_resolved",
        "mapping.aggregation_blocked",
    ] = Field(description="Audit event type")
    unified_id: str = Field(description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    conflict_type: ConflictType = Field(description="Type of conflict")
    severity: str = Field(description="Conflict severity")
    resolution_strategy: Optional[ConflictResolutionStrategy] = Field(
        default=None,
        description="Resolution strategy applied"
    )
    tenant_id: str = Field(description="Tenant ID for isolation")
    project_id: str = Field(description="Project ID for isolation")
    user_id: Optional[str] = Field(default=None, description="User ID")
    request_id: str = Field(description="Request ID for tracing")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional event details"
    )

    model_config = {"populate_by_name": True}
