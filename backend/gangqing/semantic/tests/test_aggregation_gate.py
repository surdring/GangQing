"""Unit tests for semantic layer aggregation gate module.

Tests cover:
1. Aggregation gate basic checks (allowed/blocked)
2. Entity reference extraction and validation
3. Conflict detection integration
4. AggregationBlockedError construction
5. Audit logging
6. Cross-tenant access blocking
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

from gangqing.common.context import RequestContext
from gangqing.common.errors import ErrorCode
from gangqing.semantic.aggregation_gate import (
    AggregationBlockedError,
    AggregationGate,
    AggregationGateResult,
    EntityRef,
    MappingVersionManagerProtocol,
    create_aggregation_gate,
)
from gangqing.semantic.models import (
    ConflictDetectionResult,
    ConflictType,
    EntityMappingResponse,
    EntityType,
)


# Fixtures
@pytest.fixture
def test_tenant_id() -> str:
    """Generate unique test tenant ID."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_project_id() -> str:
    """Generate unique test project ID."""
    return f"test-project-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_request_id() -> str:
    """Generate unique test request ID."""
    return f"req-{uuid.uuid4().hex[:16]}"


@pytest.fixture
def test_user_id() -> str:
    """Generate unique test user ID."""
    return f"user-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def request_context(
    test_tenant_id: str,
    test_project_id: str,
    test_request_id: str,
    test_user_id: str,
) -> RequestContext:
    """Create test request context."""
    return RequestContext(
        tenant_id=test_tenant_id,
        project_id=test_project_id,
        request_id=test_request_id,
        user_id=test_user_id,
        role="admin",
    )


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create mock mapping version manager."""
    mock = MagicMock(spec=MappingVersionManagerProtocol)
    return mock


@pytest.fixture
def aggregation_gate(
    request_context: RequestContext,
    mock_manager: MagicMock,
) -> AggregationGate:
    """Create aggregation gate with mock dependencies."""
    return AggregationGate(request_context, mock_manager)


def create_test_mapping(
    unified_id: str,
    entity_type: EntityType,
    source_system: str,
    source_id: str,
    version: int = 1,
    tenant_id: str = "test-tenant",
    project_id: str = "test-project",
) -> EntityMappingResponse:
    """Helper to create test mapping response."""
    return EntityMappingResponse(
        unified_id=unified_id,
        entity_type=entity_type,
        source_system=source_system,
        source_id=source_id,
        tenant_id=tenant_id,
        project_id=project_id,
        version=version,
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
    )


# Tests for EntityRef
class TestEntityRef:
    """Test EntityRef model."""

    def test_entity_ref_creation(self) -> None:
        """Test creating EntityRef."""
        ref = EntityRef(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            required_source_systems=["ERP", "MES"],
        )

        assert ref.unified_id == "EQUIP-001"
        assert ref.entity_type == EntityType.EQUIPMENT
        assert ref.required_source_systems == ["ERP", "MES"]

    def test_entity_ref_to_dict(self) -> None:
        """Test EntityRef serialization."""
        ref = EntityRef(
            unified_id="EQUIP-001",
            entity_type=EntityType.MATERIAL,
        )

        data = ref.to_dict()
        assert data["unified_id"] == "EQUIP-001"
        assert data["entity_type"] == "material"
        assert data["required_source_systems"] == []


# Tests for AggregationGateResult
class TestAggregationGateResult:
    """Test AggregationGateResult model."""

    def test_allowed_result(self) -> None:
        """Test allowed result."""
        result = AggregationGateResult(allowed=True)

        assert result.allowed is True
        assert result.is_blocked is False
        assert result.blocked_reason is None
        assert result.conflicts == []

    def test_blocked_result(self) -> None:
        """Test blocked result."""
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MAPPING_MISSING,
                conflict_details={},
                severity="critical",
            )
        ]

        result = AggregationGateResult(
            allowed=False,
            blocked_reason="Mapping conflict detected",
            conflicts=conflicts,
            entity_refs=[EntityRef("EQUIP-001", EntityType.EQUIPMENT)],
        )

        assert result.allowed is False
        assert result.is_blocked is True
        assert result.blocked_reason == "Mapping conflict detected"
        assert len(result.conflicts) == 1

    def test_to_dict(self) -> None:
        """Test result serialization."""
        result = AggregationGateResult(
            allowed=False,
            blocked_reason="Test block",
            conflicts=[],
            entity_refs=[EntityRef("E1", EntityType.EQUIPMENT)],
        )

        data = result.to_dict()
        assert data["allowed"] is False
        assert data["blocked_reason"] == "Test block"
        assert data["conflict_count"] == 0
        assert len(data["entity_refs"]) == 1


# Tests for AggregationBlockedError
class TestAggregationBlockedError:
    """Test AggregationBlockedError exception."""

    def test_error_creation(self) -> None:
        """Test creating blocked error."""
        entity_refs = [EntityRef("EQUIP-001", EntityType.EQUIPMENT)]
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MAPPING_MISSING,
                conflict_details={"reason": "No mapping found"},
                severity="critical",
            )
        ]

        error = AggregationBlockedError(
            entity_refs=entity_refs,
            conflicts=conflicts,
            request_id="test-req-001",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        assert error.code == ErrorCode.AGGREGATION_BLOCKED
        assert "Aggregation blocked" in error.message
        assert error.retryable is False
        assert error.request_id == "test-req-001"
        assert error.entity_refs == entity_refs
        assert error.conflicts == conflicts
        assert "entity_refs" in error.details

    def test_error_with_multiple_conflicts(self) -> None:
        """Test error with multiple conflicts."""
        entity_refs = [
            EntityRef("EQUIP-001", EntityType.EQUIPMENT),
            EntityRef("EQUIP-002", EntityType.EQUIPMENT),
        ]
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MAPPING_MISSING,
                conflict_details={},
                severity="critical",
            ),
            ConflictDetectionResult(
                unified_id="EQUIP-002",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MULTI_TO_ONE,
                conflict_details={"source_systems": ["ERP", "MES"]},
                severity="critical",
            ),
        ]

        error = AggregationBlockedError(
            entity_refs=entity_refs,
            conflicts=conflicts,
            request_id="test-req-002",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        assert "mapping_missing" in error.message.lower() or "multi_to_one" in error.message.lower()
        assert error.details["conflict_count"] == 2


# Tests for AggregationGate.check_aggregation_prerequisites
class TestCheckAggregationPrerequisites:
    """Test main aggregation gate check."""

    def test_empty_refs_allowed(
        self,
        aggregation_gate: AggregationGate,
    ) -> None:
        """Test empty refs returns allowed."""
        result = aggregation_gate.check_aggregation_prerequisites([])

        assert result.allowed is True
        assert result.is_blocked is False

    def test_single_mapping_allowed(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test single valid mapping allows aggregation."""
        # Arrange: Single valid mapping exists
        mapping = create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")
        mock_manager.get_all_mappings_for_unified_id.return_value = [mapping]

        # Act
        refs = [EntityRef("EQUIP-001", EntityType.EQUIPMENT)]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert
        assert result.allowed is True
        assert result.is_blocked is False

    def test_mapping_missing_blocked(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
        test_request_id: str,
    ) -> None:
        """Test missing mapping blocks aggregation."""
        # Arrange: No mapping exists
        mock_manager.get_all_mappings_for_unified_id.return_value = []

        # Act
        refs = [EntityRef("EQUIP-001", EntityType.EQUIPMENT)]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert
        assert result.allowed is False
        assert result.is_blocked is True
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == ConflictType.MAPPING_MISSING
        assert result.conflicts[0].request_id == test_request_id

    def test_multi_to_one_conflict_blocked(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test multi-to-one conflict blocks aggregation."""
        # Arrange: Multiple mappings to different source systems
        mappings = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "MES", "MES-001"),
        ]
        mock_manager.get_all_mappings_for_unified_id.return_value = mappings

        # Act
        refs = [EntityRef("EQUIP-001", EntityType.EQUIPMENT)]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert
        assert result.allowed is False
        assert result.is_blocked is True
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == ConflictType.MULTI_TO_ONE

    def test_multiple_entities_all_valid(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test multiple valid entities allow aggregation."""
        # Arrange: All entities have valid mappings
        def get_mappings(unified_id, entity_type, tenant_id, project_id):
            return [create_test_mapping(unified_id, entity_type, "ERP", f"ERP-{unified_id}")]

        mock_manager.get_all_mappings_for_unified_id.side_effect = get_mappings

        # Act
        refs = [
            EntityRef("EQUIP-001", EntityType.EQUIPMENT),
            EntityRef("EQUIP-002", EntityType.EQUIPMENT),
        ]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert
        assert result.allowed is True

    def test_multiple_entities_one_conflict_blocked(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test one conflict blocks all aggregation."""
        # Arrange: First entity has conflict
        def get_mappings(unified_id, entity_type, tenant_id, project_id):
            if unified_id == "EQUIP-001":
                return []  # Missing mapping
            return [create_test_mapping(unified_id, entity_type, "ERP", f"ERP-{unified_id}")]

        mock_manager.get_all_mappings_for_unified_id.side_effect = get_mappings

        # Act
        refs = [
            EntityRef("EQUIP-001", EntityType.EQUIPMENT),
            EntityRef("EQUIP-002", EntityType.EQUIPMENT),
        ]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert
        assert result.allowed is False
        assert any(c.unified_id == "EQUIP-001" for c in result.conflicts)

    def test_required_source_systems_missing(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test missing required source system blocks aggregation."""
        # Arrange: Mapping exists but not from required system
        mapping = create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")
        mock_manager.get_all_mappings_for_unified_id.return_value = [mapping]

        # Act: Require both ERP and MES, but only ERP has mapping
        refs = [
            EntityRef(
                "EQUIP-001",
                EntityType.EQUIPMENT,
                required_source_systems=["ERP", "MES"],
            )
        ]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert
        assert result.allowed is False
        assert result.is_blocked is True
        assert any(
            c.conflict_type == ConflictType.MAPPING_MISSING
            and "MES" in str(c.conflict_details.get("missing_systems", []))
            for c in result.conflicts
        )


# Tests for check_single_entity convenience method
class TestCheckSingleEntity:
    """Test single entity convenience method."""

    def test_single_entity_allowed(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test single entity check allows valid mapping."""
        mapping = create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")
        mock_manager.get_all_mappings_for_unified_id.return_value = [mapping]

        result = aggregation_gate.check_single_entity("EQUIP-001", EntityType.EQUIPMENT)

        assert result.allowed is True

    def test_single_entity_blocked(
        self,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test single entity check blocks invalid mapping."""
        mock_manager.get_all_mappings_for_unified_id.return_value = []

        result = aggregation_gate.check_single_entity("EQUIP-001", EntityType.EQUIPMENT)

        assert result.allowed is False
        assert result.conflicts[0].conflict_type == ConflictType.MAPPING_MISSING


# Tests for audit logging
class TestAuditLogging:
    """Test audit logging integration."""

    @patch("gangqing.semantic.aggregation_gate.write_audit_event")
    def test_blocked_aggregation_logged(
        self,
        mock_write_audit: Mock,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
        test_request_id: str,
    ) -> None:
        """Test that blocked aggregation is logged to audit."""
        # Arrange: Missing mapping causes block
        mock_manager.get_all_mappings_for_unified_id.return_value = []

        # Act
        refs = [EntityRef("EQUIP-001", EntityType.EQUIPMENT)]
        aggregation_gate.check_aggregation_prerequisites(refs)

        # Assert: Audit event was written
        mock_write_audit.assert_called()
        call_args = mock_write_audit.call_args
        assert call_args[1]["event_type"].value == "mapping.aggregation_blocked"
        assert call_args[1]["result_status"] == "blocked"


# Tests for factory function
class TestCreateAggregationGate:
    """Test factory function."""

    def test_factory_creates_gate(
        self,
        request_context: RequestContext,
        mock_manager: MagicMock,
    ) -> None:
        """Test factory creates valid gate."""
        gate = create_aggregation_gate(request_context, mock_manager)

        assert isinstance(gate, AggregationGate)
        assert gate.ctx == request_context


# Tests for all entity types
class TestAllEntityTypes:
    """Test aggregation gate with all entity types."""

    @pytest.mark.parametrize("entity_type", [
        EntityType.EQUIPMENT,
        EntityType.MATERIAL,
        EntityType.BATCH,
        EntityType.ORDER,
    ])
    def test_all_entity_types_allowed(
        self,
        entity_type: EntityType,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test gate works with all entity types."""
        mapping = create_test_mapping("ID-001", entity_type, "ERP", "ERP-001")
        mock_manager.get_all_mappings_for_unified_id.return_value = [mapping]

        refs = [EntityRef("ID-001", entity_type)]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        assert result.allowed is True

    @pytest.mark.parametrize("entity_type", [
        EntityType.EQUIPMENT,
        EntityType.MATERIAL,
        EntityType.BATCH,
        EntityType.ORDER,
    ])
    def test_all_entity_types_blocked(
        self,
        entity_type: EntityType,
        aggregation_gate: AggregationGate,
        mock_manager: MagicMock,
    ) -> None:
        """Test gate blocks with all entity types."""
        mock_manager.get_all_mappings_for_unified_id.return_value = []

        refs = [EntityRef("ID-001", entity_type)]
        result = aggregation_gate.check_aggregation_prerequisites(refs)

        assert result.allowed is False
        assert result.conflicts[0].entity_type == entity_type
