"""Mapping Evidence module for entity ID mapping evidence chain integration.

This module provides the MappingEvidence Pydantic model and MappingEvidenceBuilder
to capture mapping version information, conflict detection results, and
gate status into the Evidence system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


ConflictStatusLiteral = Literal["clean", "conflict", "missing"]


class MappingEvidence(BaseModel):
    """Evidence model for entity ID mapping operations.

    Captures mapping version information, source systems, conflict status,
    and gate check results for evidence chain integration.
    """

    evidence_id: str = Field(
        min_length=1,
        description="Unique evidence identifier",
    )
    unified_id: str = Field(
        min_length=1,
        description="Unified entity ID",
    )
    entity_type: Any = Field(
        description="Entity type (equipment, material, batch, order)",
    )
    mapping_version: int = Field(
        ge=1,
        description="Mapping version number",
    )
    source_systems: List[str] = Field(
        default_factory=list,
        description="List of source systems in this mapping",
    )
    conflict_status: ConflictStatusLiteral = Field(
        default="clean",
        description="Conflict detection status",
    )
    valid_from: datetime = Field(
        description="Mapping validity start timestamp",
    )
    valid_to: Optional[datetime] = Field(
        default=None,
        description="Mapping validity end timestamp (None if current)",
    )
    gate_passed: bool = Field(
        default=True,
        description="Whether aggregation gate check passed",
    )
    gate_block_reason: Optional[str] = Field(
        default=None,
        description="Reason for gate block (if gate_passed=False)",
    )
    conflict_details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detailed conflict information (if conflict detected)",
    )
    request_id: str = Field(
        min_length=1,
        description="Request ID for tracing",
    )
    tenant_id: str = Field(
        min_length=1,
        description="Tenant ID for isolation",
    )
    project_id: str = Field(
        min_length=1,
        description="Project ID for isolation",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Evidence creation timestamp",
    )

    model_config = {"populate_by_name": True}

    @field_validator("gate_block_reason")
    @classmethod
    def validate_block_reason_english(cls, v: Optional[str]) -> Optional[str]:
        """Ensure gate block reason is in English."""
        if v is None:
            return v
        # Allow ASCII characters and common punctuation
        if any(ord(c) > 127 for c in v):
            raise ValueError("Gate block reason must be in English")
        return v

    @property
    def is_current_mapping(self) -> bool:
        """Check if this represents a current (non-expired) mapping."""
        return self.valid_to is None

    @property
    def has_conflict(self) -> bool:
        """Check if this evidence indicates a mapping conflict."""
        return self.conflict_status != "clean"

    @property
    def is_blocked(self) -> bool:
        """Check if aggregation is blocked for this mapping."""
        return not self.gate_passed

    def to_sse_evidence(self) -> Dict[str, Any]:
        """Convert to SSE evidence.update payload format."""
        return {
            "evidenceId": self.evidence_id,
            "type": "mapping",
            "unifiedId": self.unified_id,
            "entityType": self.entity_type.value,
            "mappingVersion": self.mapping_version,
            "sourceSystems": self.source_systems,
            "conflictStatus": self.conflict_status,
            "validFrom": self.valid_from.isoformat(),
            "validTo": self.valid_to.isoformat() if self.valid_to else None,
            "gatePassed": self.gate_passed,
            "gateBlockReason": self.gate_block_reason,
            "conflictDetails": self.conflict_details,
            "requestId": self.request_id,
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "createdAt": self.created_at.isoformat(),
        }


class MappingEvidenceBuilder:
    """Builder for creating MappingEvidence instances.

    Provides factory methods to build evidence from various mapping operations:
    - Mapping queries
    - Conflict detection results
    - Gate check results
    """

    def __init__(self, ctx: Any) -> None:
        """Initialize builder with request context.

        Args:
            ctx: RequestContext with tenant_id, project_id, request_id
        """
        self.ctx = ctx

    def _generate_evidence_id(self) -> str:
        """Generate unique evidence ID."""
        return f"ev:mapping:{uuid4().hex[:16]}"

    def from_mapping_response(
        self,
        mapping: Any,
        *,
        gate_passed: bool = True,
        gate_block_reason: Optional[str] = None,
        conflict_status: ConflictStatusLiteral = "clean",
        conflict_details: Optional[Dict[str, Any]] = None,
    ) -> MappingEvidence:
        """Build evidence from a mapping response.

        Args:
            mapping: Entity mapping response
            gate_passed: Whether gate check passed
            gate_block_reason: Gate block reason (if blocked)
            conflict_status: Conflict detection status
            conflict_details: Conflict details (if any)

        Returns:
            MappingEvidence instance
        """
        return MappingEvidence(
            evidence_id=self._generate_evidence_id(),
            unified_id=mapping.unified_id,
            entity_type=mapping.entity_type,
            mapping_version=mapping.version,
            source_systems=[mapping.source_system],
            conflict_status=conflict_status,
            valid_from=mapping.valid_from,
            valid_to=mapping.valid_to,
            gate_passed=gate_passed,
            gate_block_reason=gate_block_reason,
            conflict_details=conflict_details,
            request_id=self.ctx.request_id,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
        )

    def from_mapping_list(
        self,
        unified_id: str,
        entity_type: Any,
        mappings: List[Any],
        *,
        gate_passed: bool = True,
        gate_block_reason: Optional[str] = None,
        conflict_result: Optional[Any] = None,
    ) -> MappingEvidence:
        """Build evidence from multiple mappings (e.g., conflict case).

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type
            mappings: List of mappings (may indicate conflicts)
            gate_passed: Whether gate check passed
            gate_block_reason: Gate block reason (if blocked)
            conflict_result: Conflict detection result (if any)

        Returns:
            MappingEvidence instance
        """
        # Determine conflict status
        conflict_status: ConflictStatusLiteral = "clean"
        conflict_details: Optional[Dict[str, Any]] = None

        if conflict_result is not None:
            # Check if this is a MAPPING_MISSING conflict
            conflict_type_value = getattr(conflict_result.conflict_type, "value", str(conflict_result.conflict_type))
            is_missing = conflict_type_value == "mapping_missing"
            conflict_status = "conflict" if not is_missing else "missing"
            conflict_details = {
                "conflict_type": conflict_type_value,
                "severity": conflict_result.severity,
                "details": conflict_result.conflict_details,
            }
        elif not mappings:
            conflict_status = "missing"
            conflict_details = {"reason": "No mappings found for unified_id"}
        elif len(mappings) > 1:
            # Multiple mappings - check if conflict
            source_systems = list({m.source_system for m in mappings})
            if len(source_systems) > 1:
                conflict_status = "conflict"
                conflict_details = {
                    "conflict_type": "multi_to_one",
                    "mapping_count": len(mappings),
                    "source_systems": source_systems,
                }

        # Aggregate source systems
        all_source_systems = list({m.source_system for m in mappings})

        # Use max version if multiple mappings
        max_version = max((m.version for m in mappings), default=1) if mappings else 1

        # Use earliest valid_from and latest valid_to
        valid_from = min((m.valid_from for m in mappings), default=datetime.now(timezone.utc)) if mappings else datetime.now(timezone.utc)
        valid_to = None
        if mappings:
            non_null_valid_to = [m.valid_to for m in mappings if m.valid_to is not None]
            if non_null_valid_to:
                valid_to = max(non_null_valid_to)

        return MappingEvidence(
            evidence_id=self._generate_evidence_id(),
            unified_id=unified_id,
            entity_type=entity_type,
            mapping_version=max_version,
            source_systems=all_source_systems,
            conflict_status=conflict_status,
            valid_from=valid_from,
            valid_to=valid_to,
            gate_passed=gate_passed,
            gate_block_reason=gate_block_reason,
            conflict_details=conflict_details,
            request_id=self.ctx.request_id,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
        )

    def from_conflict_detection(
        self,
        unified_id: str,
        entity_type: Any,
        mappings: List[Any],
        conflict: Any,
        *,
        gate_passed: bool = False,
        gate_block_reason: Optional[str] = None,
    ) -> MappingEvidence:
        """Build evidence from conflict detection result.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type
            mappings: Current mappings (may be empty)
            conflict: Conflict detection result
            gate_passed: Whether gate check passed
            gate_block_reason: Gate block reason

        Returns:
            MappingEvidence instance with conflict information
        """
        conflict_type_value = getattr(conflict.conflict_type, "value", str(conflict.conflict_type))
        is_missing = conflict_type_value == "mapping_missing"
        conflict_status: ConflictStatusLiteral = "missing" if is_missing else "conflict"

        source_systems = list({m.source_system for m in mappings})

        # Get version from mappings if available
        version = mappings[0].version if mappings else 1
        valid_from = mappings[0].valid_from if mappings else datetime.now(timezone.utc)
        valid_to = mappings[0].valid_to if mappings else None

        if gate_block_reason is None and not gate_passed:
            conflict_type_value = getattr(conflict.conflict_type, "value", str(conflict.conflict_type))
            gate_block_reason = f"Conflict detected: {conflict_type_value}"

        return MappingEvidence(
            evidence_id=self._generate_evidence_id(),
            unified_id=unified_id,
            entity_type=entity_type,
            mapping_version=version,
            source_systems=source_systems,
            conflict_status=conflict_status,
            valid_from=valid_from,
            valid_to=valid_to,
            gate_passed=gate_passed,
            gate_block_reason=gate_block_reason,
            conflict_details={
                "conflict_type": conflict_type_value,
                "severity": conflict.severity,
                "details": conflict.conflict_details,
                "detected_at": conflict.detected_at.isoformat(),
            },
            request_id=self.ctx.request_id,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
        )

    def from_gate_result(
        self,
        unified_id: str,
        entity_type: Any,
        mapping: Optional[Any],
        gate_passed: bool,
        *,
        gate_block_reason: Optional[str] = None,
        conflicts: Optional[List[Any]] = None,
    ) -> MappingEvidence:
        """Build evidence from aggregation gate check result.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type
            mapping: Current mapping (if found)
            gate_passed: Whether gate check passed
            gate_block_reason: Gate block reason (if blocked)
            conflicts: List of conflicts that caused block

        Returns:
            MappingEvidence instance
        """
        conflict_status: ConflictStatusLiteral = "clean"
        conflict_details: Optional[Dict[str, Any]] = None

        if conflicts:
            primary_conflict = conflicts[0]
            primary_conflict_type = getattr(primary_conflict.conflict_type, "value", str(primary_conflict.conflict_type))
            conflict_status = "missing" if primary_conflict_type == "mapping_missing" else "conflict"
            conflict_details = {
                "conflict_count": len(conflicts),
                "primary_conflict": {
                    "type": primary_conflict_type,
                    "severity": primary_conflict.severity,
                },
                "all_conflicts": [
                    {
                        "type": getattr(c.conflict_type, "value", str(c.conflict_type)),
                        "severity": c.severity,
                    }
                    for c in conflicts
                ],
            }
        elif mapping is None:
            conflict_status = "missing"
            conflict_details = {"reason": "Mapping not found for gate check"}

        if mapping is not None:
            return MappingEvidence(
                evidence_id=self._generate_evidence_id(),
                unified_id=unified_id,
                entity_type=entity_type,
                mapping_version=mapping.version,
                source_systems=[mapping.source_system],
                conflict_status=conflict_status,
                valid_from=mapping.valid_from,
                valid_to=mapping.valid_to,
                gate_passed=gate_passed,
                gate_block_reason=gate_block_reason,
                conflict_details=conflict_details,
                request_id=self.ctx.request_id,
                tenant_id=self.ctx.tenant_id,
                project_id=self.ctx.project_id,
            )
        else:
            return MappingEvidence(
                evidence_id=self._generate_evidence_id(),
                unified_id=unified_id,
                entity_type=entity_type,
                mapping_version=1,
                source_systems=[],
                conflict_status=conflict_status,
                valid_from=datetime.now(timezone.utc),
                valid_to=None,
                gate_passed=gate_passed,
                gate_block_reason=gate_block_reason or "Mapping not found",
                conflict_details=conflict_details,
                request_id=self.ctx.request_id,
                tenant_id=self.ctx.tenant_id,
                project_id=self.ctx.project_id,
            )


def create_mapping_evidence_builder(ctx: Any) -> MappingEvidenceBuilder:
    """Factory function to create a MappingEvidenceBuilder.

    Args:
        ctx: RequestContext with tenant_id, project_id, request_id

    Returns:
        MappingEvidenceBuilder instance
    """
    return MappingEvidenceBuilder(ctx)
