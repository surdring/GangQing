"""Unit tests for mapping evidence module.

Tests the MappingEvidence model and MappingEvidenceBuilder class.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from gangqing.semantic.mapping_evidence import (
    ConflictStatusLiteral,
    MappingEvidence,
    MappingEvidenceBuilder,
    create_mapping_evidence_builder,
)
from gangqing.semantic.models import (
    ConflictDetectionResult,
    ConflictType,
    EntityMappingResponse,
    EntityType,
)


class TestMappingEvidence:
    """Tests for MappingEvidence model."""

    def test_mapping_evidence_creation(self) -> None:
        """Test basic MappingEvidence creation."""
        evidence = MappingEvidence(
            evidence_id="ev:mapping:test123",
            unified_id="equipment-001",
            entity_type=EntityType.EQUIPMENT,
            mapping_version=1,
            source_systems=["ERP", "MES"],
            conflict_status="clean",
            valid_from=datetime.now(timezone.utc),
            valid_to=None,
            gate_passed=True,
            gate_block_reason=None,
            request_id="req-123",
            tenant_id="tenant-001",
            project_id="project-001",
        )

        assert evidence.evidence_id == "ev:mapping:test123"
        assert evidence.unified_id == "equipment-001"
        assert evidence.entity_type == EntityType.EQUIPMENT
        assert evidence.mapping_version == 1
        assert evidence.source_systems == ["ERP", "MES"]
        assert evidence.conflict_status == "clean"
        assert evidence.gate_passed is True
        assert evidence.is_current_mapping is True
        assert evidence.has_conflict is False
        assert evidence.is_blocked is False

    def test_mapping_evidence_conflict_status(self) -> None:
        """Test conflict status properties."""
        # Clean status
        clean_evidence = MappingEvidence(
            evidence_id="ev:1",
            unified_id="u1",
            entity_type=EntityType.MATERIAL,
            mapping_version=1,
            source_systems=["ERP"],
            conflict_status="clean",
            valid_from=datetime.now(timezone.utc),
            gate_passed=True,
            request_id="r1",
            tenant_id="t1",
            project_id="p1",
        )
        assert clean_evidence.has_conflict is False
        assert clean_evidence.conflict_status == "clean"

        # Conflict status
        conflict_evidence = MappingEvidence(
            evidence_id="ev:2",
            unified_id="u2",
            entity_type=EntityType.MATERIAL,
            mapping_version=1,
            source_systems=["ERP", "MES"],
            conflict_status="conflict",
            valid_from=datetime.now(timezone.utc),
            gate_passed=False,
            gate_block_reason="Multi-to-one conflict detected",
            request_id="r1",
            tenant_id="t1",
            project_id="p1",
        )
        assert conflict_evidence.has_conflict is True
        assert conflict_evidence.is_blocked is True

        # Missing status
        missing_evidence = MappingEvidence(
            evidence_id="ev:3",
            unified_id="u3",
            entity_type=EntityType.BATCH,
            mapping_version=1,
            source_systems=[],
            conflict_status="missing",
            valid_from=datetime.now(timezone.utc),
            gate_passed=False,
            gate_block_reason="Mapping not found",
            request_id="r1",
            tenant_id="t1",
            project_id="p1",
        )
        assert missing_evidence.has_conflict is True
        assert missing_evidence.conflict_status == "missing"

    def test_mapping_evidence_block_reason_english_validation(self) -> None:
        """Test that block reason must be in English."""
        # Valid English reason
        evidence = MappingEvidence(
            evidence_id="ev:1",
            unified_id="u1",
            entity_type=EntityType.EQUIPMENT,
            mapping_version=1,
            source_systems=["ERP"],
            conflict_status="conflict",
            valid_from=datetime.now(timezone.utc),
            gate_passed=False,
            gate_block_reason="Mapping conflict detected in ERP",
            request_id="r1",
            tenant_id="t1",
            project_id="p1",
        )
        assert evidence.gate_block_reason == "Mapping conflict detected in ERP"

    def test_mapping_evidence_to_sse_format(self) -> None:
        """Test conversion to SSE format."""
        now = datetime.now(timezone.utc)
        evidence = MappingEvidence(
            evidence_id="ev:mapping:abc123",
            unified_id="order-001",
            entity_type=EntityType.ORDER,
            mapping_version=2,
            source_systems=["ERP", "DCS"],
            conflict_status="clean",
            valid_from=now,
            valid_to=None,
            gate_passed=True,
            gate_block_reason=None,
            request_id="req-test",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        sse_format = evidence.to_sse_evidence()

        assert sse_format["evidenceId"] == "ev:mapping:abc123"
        assert sse_format["type"] == "mapping"
        assert sse_format["unifiedId"] == "order-001"
        assert sse_format["entityType"] == "order"
        assert sse_format["mappingVersion"] == 2
        assert sse_format["sourceSystems"] == ["ERP", "DCS"]
        assert sse_format["conflictStatus"] == "clean"
        assert sse_format["gatePassed"] is True
        assert sse_format["validFrom"] == now.isoformat()
        assert sse_format["validTo"] is None


class TestMappingEvidenceBuilder:
    """Tests for MappingEvidenceBuilder class."""

    @pytest.fixture
    def mock_context(self) -> Any:
        """Create mock request context."""
        ctx = MagicMock()
        ctx.request_id = "req-test-123"
        ctx.tenant_id = "tenant-001"
        ctx.project_id = "project-001"
        ctx.user_id = "user-123"
        return ctx

    @pytest.fixture
    def builder(self, mock_context: Any) -> MappingEvidenceBuilder:
        """Create evidence builder."""
        return MappingEvidenceBuilder(mock_context)

    @pytest.fixture
    def sample_mapping(self) -> EntityMappingResponse:
        """Create sample mapping response."""
        return EntityMappingResponse(
            unified_id="equipment-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="ERP",
            source_id="erp-equip-123",
            tenant_id="tenant-001",
            project_id="project-001",
            version=1,
            valid_from=datetime.now(timezone.utc),
            valid_to=None,
            created_by="admin",
            metadata={"location": "Line A"},
        )

    def test_builder_initialization(self, mock_context: Any) -> None:
        """Test builder initialization."""
        builder = MappingEvidenceBuilder(mock_context)
        assert builder.ctx == mock_context

    def test_from_mapping_response(self, builder: MappingEvidenceBuilder, sample_mapping: EntityMappingResponse) -> None:
        """Test building evidence from single mapping response."""
        evidence = builder.from_mapping_response(sample_mapping)

        assert evidence.unified_id == "equipment-001"
        assert evidence.entity_type == EntityType.EQUIPMENT
        assert evidence.mapping_version == 1
        assert evidence.source_systems == ["ERP"]
        assert evidence.conflict_status == "clean"
        assert evidence.gate_passed is True
        assert evidence.request_id == "req-test-123"
        assert evidence.tenant_id == "tenant-001"
        assert evidence.project_id == "project-001"
        assert evidence.evidence_id.startswith("ev:mapping:")

    def test_from_mapping_response_with_block(self, builder: MappingEvidenceBuilder, sample_mapping: EntityMappingResponse) -> None:
        """Test building evidence with gate block."""
        evidence = builder.from_mapping_response(
            sample_mapping,
            gate_passed=False,
            gate_block_reason="Aggregation not allowed",
            conflict_status="conflict",
        )

        assert evidence.gate_passed is False
        assert evidence.gate_block_reason == "Aggregation not allowed"
        assert evidence.conflict_status == "conflict"
        assert evidence.is_blocked is True

    def test_from_mapping_list_clean(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from clean mapping list."""
        mappings = [
            EntityMappingResponse(
                unified_id="mat-001",
                entity_type=EntityType.MATERIAL,
                source_system="ERP",
                source_id="erp-mat-001",
                tenant_id="tenant-001",
                project_id="project-001",
                version=1,
                valid_from=datetime.now(timezone.utc),
                valid_to=None,
            ),
        ]

        evidence = builder.from_mapping_list("mat-001", EntityType.MATERIAL, mappings)

        assert evidence.unified_id == "mat-001"
        assert evidence.conflict_status == "clean"
        assert evidence.mapping_version == 1
        assert evidence.source_systems == ["ERP"]
        assert evidence.gate_passed is True

    def test_from_mapping_list_conflict(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from conflicting mapping list."""
        now = datetime.now(timezone.utc)
        mappings = [
            EntityMappingResponse(
                unified_id="equip-001",
                entity_type=EntityType.EQUIPMENT,
                source_system="ERP",
                source_id="erp-001",
                tenant_id="tenant-001",
                project_id="project-001",
                version=1,
                valid_from=now,
                valid_to=None,
            ),
            EntityMappingResponse(
                unified_id="equip-001",
                entity_type=EntityType.EQUIPMENT,
                source_system="MES",
                source_id="mes-001",
                tenant_id="tenant-001",
                project_id="project-001",
                version=2,
                valid_from=now,
                valid_to=None,
            ),
        ]

        evidence = builder.from_mapping_list(
            "equip-001", EntityType.EQUIPMENT, mappings
        )

        assert evidence.conflict_status == "conflict"
        assert set(evidence.source_systems) == {"ERP", "MES"}
        assert evidence.mapping_version == 2  # Max version
        assert evidence.conflict_details is not None
        assert evidence.conflict_details.get("conflict_type") == ConflictType.MULTI_TO_ONE.value

    def test_from_mapping_list_empty(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from empty mapping list (missing)."""
        evidence = builder.from_mapping_list(
            "missing-001", EntityType.BATCH, []
        )

        assert evidence.conflict_status == "missing"
        assert evidence.source_systems == []
        assert evidence.conflict_details is not None

    def test_from_conflict_detection(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from conflict detection result."""
        now = datetime.now(timezone.utc)
        mappings = [
            EntityMappingResponse(
                unified_id="conflict-001",
                entity_type=EntityType.ORDER,
                source_system="ERP",
                source_id="erp-001",
                tenant_id="tenant-001",
                project_id="project-001",
                version=1,
                valid_from=now,
                valid_to=None,
            ),
        ]

        conflict = ConflictDetectionResult(
            unified_id="conflict-001",
            entity_type=EntityType.ORDER,
            conflict_type=ConflictType.CROSS_SYSTEM,
            conflict_details={"reason": "Source ID conflict"},
            severity="warning",
            request_id="req-test-123",
        )

        evidence = builder.from_conflict_detection(
            "conflict-001", EntityType.ORDER, mappings, conflict
        )

        assert evidence.conflict_status == "conflict"
        assert evidence.gate_passed is False
        assert evidence.gate_block_reason is not None
        assert evidence.conflict_details is not None
        assert evidence.conflict_details["conflict_type"] == ConflictType.CROSS_SYSTEM.value

    def test_from_conflict_detection_missing(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from missing mapping conflict."""
        conflict = ConflictDetectionResult(
            unified_id="missing-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MAPPING_MISSING,
            conflict_details={"reason": "No mapping found"},
            severity="critical",
        )

        evidence = builder.from_conflict_detection(
            "missing-001", EntityType.EQUIPMENT, [], conflict
        )

        assert evidence.conflict_status == "missing"
        assert evidence.source_systems == []

    def test_from_gate_result_allowed(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from successful gate check."""
        mapping = EntityMappingResponse(
            unified_id="gate-001",
            entity_type=EntityType.MATERIAL,
            source_system="DCS",
            source_id="dcs-001",
            tenant_id="tenant-001",
            project_id="project-001",
            version=3,
            valid_from=datetime.now(timezone.utc),
            valid_to=None,
        )

        evidence = builder.from_gate_result(
            "gate-001", EntityType.MATERIAL, mapping, gate_passed=True
        )

        assert evidence.gate_passed is True
        assert evidence.gate_block_reason is None
        assert evidence.conflict_status == "clean"
        assert evidence.mapping_version == 3

    def test_from_gate_result_blocked(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence from blocked gate check."""
        conflicts = [
            ConflictDetectionResult(
                unified_id="block-001",
                entity_type=EntityType.BATCH,
                conflict_type=ConflictType.MULTI_TO_ONE,
                conflict_details={"mapping_count": 2},
                severity="critical",
            ),
        ]

        evidence = builder.from_gate_result(
            "block-001",
            EntityType.BATCH,
            None,
            gate_passed=False,
            conflicts=conflicts,
        )

        assert evidence.gate_passed is False
        assert evidence.gate_block_reason is not None
        assert evidence.conflict_status == "conflict"
        assert evidence.conflict_details is not None
        assert evidence.conflict_details["conflict_count"] == 1

    def test_from_gate_result_no_mapping(self, builder: MappingEvidenceBuilder) -> None:
        """Test building evidence when mapping not found in gate check."""
        evidence = builder.from_gate_result(
            "notfound-001",
            EntityType.ORDER,
            None,
            gate_passed=False,
            gate_block_reason="Mapping not found for aggregation",
        )

        assert evidence.gate_passed is False
        assert evidence.conflict_status == "missing"
        assert evidence.mapping_version == 1  # Default


class TestCreateMappingEvidenceBuilder:
    """Tests for factory function."""

    def test_factory_function(self) -> None:
        """Test create_mapping_evidence_builder factory."""
        ctx = MagicMock()
        ctx.request_id = "factory-test"
        ctx.tenant_id = "t1"
        ctx.project_id = "p1"

        builder = create_mapping_evidence_builder(ctx)

        assert isinstance(builder, MappingEvidenceBuilder)
        assert builder.ctx == ctx


class TestEvidenceIntegration:
    """Integration tests for evidence in mapping operations."""

    def test_evidence_request_id_tracing(self) -> None:
        """Test that request_id is properly traced through evidence."""
        ctx = MagicMock()
        ctx.request_id = "trace-123"
        ctx.tenant_id = "t1"
        ctx.project_id = "p1"

        builder = MappingEvidenceBuilder(ctx)

        mapping = EntityMappingResponse(
            unified_id="test-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="ERP",
            source_id="erp-001",
            tenant_id="t1",
            project_id="p1",
            version=1,
            valid_from=datetime.now(timezone.utc),
        )

        evidence = builder.from_mapping_response(mapping)

        assert evidence.request_id == "trace-123"

        # Verify SSE format includes request_id
        sse = evidence.to_sse_evidence()
        assert sse["requestId"] == "trace-123"

    def test_evidence_contains_all_required_fields(self) -> None:
        """Verify evidence contains all fields required by T56.4 spec."""
        ctx = MagicMock()
        ctx.request_id = "req-123"
        ctx.tenant_id = "tenant-1"
        ctx.project_id = "project-1"

        builder = MappingEvidenceBuilder(ctx)

        mapping = EntityMappingResponse(
            unified_id="test-001",
            entity_type=EntityType.MATERIAL,
            source_system="MES",
            source_id="mes-001",
            tenant_id="tenant-1",
            project_id="project-1",
            version=5,
            valid_from=datetime.now(timezone.utc),
        )

        evidence = builder.from_mapping_response(mapping)

        # Verify all required fields from T56.4
        assert evidence.evidence_id is not None
        assert evidence.unified_id is not None
        assert evidence.entity_type is not None
        assert evidence.mapping_version is not None
        assert evidence.source_systems is not None
        assert evidence.conflict_status is not None
        assert evidence.valid_from is not None
        assert evidence.gate_passed is not None
        assert evidence.request_id is not None
        assert evidence.tenant_id is not None
        assert evidence.project_id is not None
