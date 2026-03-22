"""Unit tests for semantic layer conflict detection module.

Tests cover:
1. Conflict detection by unified_id (MULTI_TO_ONE, MAPPING_MISSING)
2. Conflict detection by source_id (CROSS_SYSTEM)
3. Multi-to-one conflict scanning
4. Mapping consistency validation
5. Aggregation blocking checks
6. Error mapping to EVIDENCE_MISMATCH
7. Degraded response generation
8. Resolution strategy selection
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import MagicMock, Mock

import pytest

from gangqing.common.errors import AppError, ErrorCode
from gangqing.semantic.conflict_detector import ConflictDetector
from gangqing.semantic.mapping_errors import (
    build_aggregation_blocked_error,
    error_response_to_dict,
    map_conflict_to_error,
)
from gangqing.semantic.mapping_fallback import (
    create_degraded_response,
    merge_degraded_results,
    resolve_conflict_strategy,
    should_degrade,
)
from gangqing.semantic.models import (
    ConflictDetectionResult,
    ConflictResolutionStrategy,
    ConflictType,
    DegradedResult,
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
def mock_manager() -> MagicMock:
    """Create mock mapping version manager."""
    return MagicMock()


@pytest.fixture
def mock_audit_logger() -> MagicMock:
    """Create mock audit logger."""
    return MagicMock()


@pytest.fixture
def detector(mock_manager: MagicMock, mock_audit_logger: MagicMock) -> ConflictDetector:
    """Create conflict detector with mock dependencies."""
    return ConflictDetector(
        mapping_version_manager=mock_manager,
        audit_logger=mock_audit_logger,
    )


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


# Tests for detect_by_unified_id
class TestDetectByUnifiedId:
    """Test conflict detection by unified_id."""

    def test_mapping_missing(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
        test_request_id: str,
    ) -> None:
        """Test detection of missing mapping."""
        # Arrange: No mappings exist
        mock_manager.get_all_mappings_for_unified_id.return_value = []

        # Act
        conflicts = detector.detect_by_unified_id(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
            request_id=test_request_id,
        )

        # Assert
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.MAPPING_MISSING
        assert conflict.severity == "critical"
        assert conflict.unified_id == "EQUIP-001"
        assert conflict.entity_type == EntityType.EQUIPMENT
        assert conflict.request_id == test_request_id
        assert conflict.is_blocking is True

    def test_no_conflict_single_mapping(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test no conflict detected with single valid mapping."""
        # Arrange: Single mapping exists
        mapping = create_test_mapping(
            "EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"
        )
        mock_manager.get_all_mappings_for_unified_id.return_value = [mapping]

        # Act
        conflicts = detector.detect_by_unified_id(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert len(conflicts) == 0

    def test_multi_to_one_conflict(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
        test_request_id: str,
    ) -> None:
        """Test detection of multi-to-one conflict across systems."""
        # Arrange: Multiple mappings to different source systems
        mappings = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "MES", "MES-001"),
        ]
        mock_manager.get_all_mappings_for_unified_id.return_value = mappings

        # Act
        conflicts = detector.detect_by_unified_id(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
            request_id=test_request_id,
        )

        # Assert
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.MULTI_TO_ONE
        assert conflict.severity == "critical"
        assert conflict.is_blocking is True
        assert "ERP" in conflict.conflict_details["source_systems"]
        assert "MES" in conflict.conflict_details["source_systems"]
        assert conflict.request_id == test_request_id

    def test_same_system_multiple_ids_warning(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test warning for multiple IDs in same system."""
        # Arrange: Multiple mappings in same system
        mappings = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-002"),
        ]
        mock_manager.get_all_mappings_for_unified_id.return_value = mappings

        # Act
        conflicts = detector.detect_by_unified_id(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.CROSS_SYSTEM
        assert conflict.severity == "warning"


# Tests for detect_by_source_id
class TestDetectBySourceId:
    """Test conflict detection by source_id."""

    def test_no_conflict_single_mapping(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test no conflict when source_id maps to single unified_id."""
        # Arrange: Single mapping
        mapping = create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")
        mock_manager.get_mappings_by_source_id.return_value = [mapping]

        # Act
        conflicts = detector.detect_by_source_id(
            source_system="ERP",
            source_id="ERP-001",
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert len(conflicts) == 0

    def test_cross_system_conflict(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
        test_request_id: str,
    ) -> None:
        """Test detection when source_id maps to multiple unified_ids."""
        # Arrange: Same source_id maps to multiple unified_ids
        mappings = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
            create_test_mapping("EQUIP-002", EntityType.EQUIPMENT, "ERP", "ERP-001"),
        ]
        mock_manager.get_mappings_by_source_id.return_value = mappings

        # Act
        conflicts = detector.detect_by_source_id(
            source_system="ERP",
            source_id="ERP-001",
            tenant_id=test_tenant_id,
            project_id=test_project_id,
            request_id=test_request_id,
        )

        # Assert
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.CROSS_SYSTEM
        assert conflict.severity == "warning"
        assert "EQUIP-001" in conflict.conflict_details["unified_ids"]
        assert "EQUIP-002" in conflict.conflict_details["unified_ids"]


# Tests for detect_multi_to_one
class TestDetectMultiToOne:
    """Test multi-to-one conflict scanning."""

    def test_no_conflicts(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test no conflicts found in clean data."""
        # Arrange: No multi-mappings
        mock_manager.get_unified_ids_with_multiple_mappings.return_value = {}

        # Act
        conflicts = detector.detect_multi_to_one(
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert len(conflicts) == 0

    def test_multiple_conflicts_found(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
        test_request_id: str,
    ) -> None:
        """Test detection of multiple multi-to-one conflicts."""
        # Arrange: Multiple entities with conflicts
        mappings_map = {
            "EQUIP-001": [
                create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
                create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "MES", "MES-001"),
            ],
            "EQUIP-002": [
                create_test_mapping("EQUIP-002", EntityType.EQUIPMENT, "ERP", "ERP-002"),
                create_test_mapping("EQUIP-002", EntityType.EQUIPMENT, "DCS", "DCS-002"),
            ],
        }
        mock_manager.get_unified_ids_with_multiple_mappings.return_value = mappings_map

        # Act
        conflicts = detector.detect_multi_to_one(
            tenant_id=test_tenant_id,
            project_id=test_project_id,
            request_id=test_request_id,
        )

        # Assert
        assert len(conflicts) == 2
        for conflict in conflicts:
            assert conflict.conflict_type == ConflictType.MULTI_TO_ONE
            assert conflict.severity == "critical"


# Tests for validate_mapping_consistency
class TestValidateMappingConsistency:
    """Test mapping consistency validation."""

    def test_empty_mappings_passes(
        self,
        detector: ConflictDetector,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test empty mappings pass validation."""
        # Act
        result = detector.validate_mapping_consistency(
            mappings=[],
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert result is None

    def test_single_mapping_passes(
        self,
        detector: ConflictDetector,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test single mapping passes validation."""
        # Arrange
        mappings = [create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")]

        # Act
        result = detector.validate_mapping_consistency(
            mappings=mappings,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert result is None

    def test_same_system_multiple_mappings_passes(
        self,
        detector: ConflictDetector,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test same system multiple mappings passes (for aggregation)."""
        # Arrange: Same unified_id, different source systems (valid for aggregation)
        # Actually this should fail - multi-to-one is always a conflict
        mappings = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "MES", "MES-001"),
        ]

        # Act
        result = detector.validate_mapping_consistency(
            mappings=mappings,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert result is not None
        assert result.conflict_type == ConflictType.MULTI_TO_ONE


# Tests for check_aggregation_blocked
class TestCheckAggregationBlocked:
    """Test aggregation blocking checks."""

    def test_no_conflicts_allows_aggregation(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test aggregation allowed when no conflicts."""
        # Arrange: No conflicts for any ID
        mock_manager.get_all_mappings_for_unified_id.return_value = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")
        ]

        # Act
        blocked, conflicts = detector.check_aggregation_blocked(
            unified_ids=["EQUIP-001"],
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert blocked is False
        assert len(conflicts) == 0

    def test_critical_conflict_blocks_aggregation(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        mock_audit_logger: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
        test_request_id: str,
    ) -> None:
        """Test aggregation blocked when critical conflict exists."""
        # Arrange: Missing mapping
        mock_manager.get_all_mappings_for_unified_id.return_value = []

        # Act
        blocked, conflicts = detector.check_aggregation_blocked(
            unified_ids=["EQUIP-001"],
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
            request_id=test_request_id,
        )

        # Assert
        assert blocked is True
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.MAPPING_MISSING
        # Verify audit log was called
        mock_audit_logger.log_mapping_event.assert_called()

    def test_multiple_ids_with_partial_conflicts(
        self,
        detector: ConflictDetector,
        mock_manager: MagicMock,
        test_tenant_id: str,
        test_project_id: str,
    ) -> None:
        """Test aggregation blocked if any ID has critical conflict."""
        # Arrange: First ID has mapping, second doesn't
        def side_effect(*, unified_id: str, **kwargs: Any) -> List[Any]:
            if unified_id == "EQUIP-001":
                return [create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001")]
            return []  # EQUIP-002 missing

        mock_manager.get_all_mappings_for_unified_id.side_effect = side_effect

        # Act
        blocked, conflicts = detector.check_aggregation_blocked(
            unified_ids=["EQUIP-001", "EQUIP-002"],
            entity_type=EntityType.EQUIPMENT,
            tenant_id=test_tenant_id,
            project_id=test_project_id,
        )

        # Assert
        assert blocked is True
        assert len(conflicts) == 1
        assert conflicts[0].unified_id == "EQUIP-002"


# Tests for error mapping
class TestMapConflictToError:
    """Test mapping conflicts to EVIDENCE_MISMATCH errors."""

    def test_multi_to_one_error_message(
        self,
        test_request_id: str,
    ) -> None:
        """Test error message for multi-to-one conflict."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MULTI_TO_ONE,
            conflict_details={
                "source_systems": ["ERP", "MES"],
                "source_ids": ["ERP-001", "MES-001"],
            },
            severity="critical",
        )

        # Act
        error = map_conflict_to_error(conflict, request_id=test_request_id)

        # Assert
        assert error.code == ErrorCode.EVIDENCE_MISMATCH
        assert error.retryable is False
        assert error.request_id == test_request_id
        assert "MULTI_TO_ONE" in error.message
        assert "equipment" in error.message.lower()
        assert "ERP" in error.message
        assert "MES" in error.message

    def test_mapping_missing_error_message(
        self,
        test_request_id: str,
    ) -> None:
        """Test error message for missing mapping."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MAPPING_MISSING,
            conflict_details={"reason": "No mapping exists"},
            severity="critical",
        )

        # Act
        error = map_conflict_to_error(conflict, request_id=test_request_id)

        # Assert
        assert error.code == ErrorCode.EVIDENCE_MISMATCH
        assert "MAPPING_MISSING" in error.message
        assert "EQUIP-001" in error.message
        assert error.details is not None
        assert error.details["conflict_type"] == "mapping_missing"

    def test_error_details_structure(
        self,
        test_request_id: str,
    ) -> None:
        """Test error details contains required fields."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.VERSION_MISMATCH,
            conflict_details={
                "expected_version": 1,
                "actual_version": 2,
            },
            severity="warning",
        )

        # Act
        error = map_conflict_to_error(conflict, request_id=test_request_id)
        response = error.to_response()

        # Assert
        assert response.code == "EVIDENCE_MISMATCH"
        assert response.retryable is False
        assert response.request_id == test_request_id
        assert response.details is not None
        assert response.details["unified_id"] == "EQUIP-001"
        assert response.details["entity_type"] == "equipment"
        assert response.details["severity"] == "warning"
        assert "detected_at" in response.details

    def test_error_response_to_dict(
        self,
        test_request_id: str,
    ) -> None:
        """Test conversion to dict for JSON serialization."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MAPPING_MISSING,
            conflict_details={},
            severity="critical",
        )
        error = map_conflict_to_error(conflict, request_id=test_request_id)

        # Act
        error_dict = error_response_to_dict(error)

        # Assert
        assert error_dict["code"] == "EVIDENCE_MISMATCH"
        assert error_dict["retryable"] is False
        assert error_dict["requestId"] == test_request_id
        assert "message" in error_dict
        assert "details" in error_dict

    def test_aggregation_blocked_error(
        self,
        test_request_id: str,
    ) -> None:
        """Test error for aggregation blocked scenario."""
        # Arrange
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MULTI_TO_ONE,
                conflict_details={},
                severity="critical",
            ),
        ]

        # Act
        error = build_aggregation_blocked_error(
            unified_ids=["EQUIP-001", "EQUIP-002"],
            entity_type="equipment",
            conflicts=conflicts,
            request_id=test_request_id,
        )

        # Assert
        assert error.code == ErrorCode.EVIDENCE_MISMATCH
        assert "blocked" in error.message.lower()
        assert "EQUIP-001" in error.message or "2" in error.message
        assert error.details["conflict_count"] == 1
        assert error.retryable is False


# Tests for degradation strategy
class TestCreateDegradedResponse:
    """Test degraded response generation."""

    def test_degraded_response_structure(
        self,
        test_request_id: str,
    ) -> None:
        """Test degraded response contains required fields."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MULTI_TO_ONE,
            conflict_details={
                "source_systems": ["ERP", "MES"],
                "source_ids": ["ERP-001", "MES-001"],
            },
            severity="critical",
        )
        mappings = [
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "ERP", "ERP-001"),
            create_test_mapping("EQUIP-001", EntityType.EQUIPMENT, "MES", "MES-001"),
        ]

        # Act
        result = create_degraded_response(
            conflict=conflict,
            available_mappings=mappings,
            request_id=test_request_id,
        )

        # Assert
        assert result.unified_id == "EQUIP-001"
        assert result.entity_type == EntityType.EQUIPMENT
        assert result.conflict_type == ConflictType.MULTI_TO_ONE
        assert len(result.available_sources) == 2
        assert result.requires_manual_review is True
        assert result.request_id == test_request_id
        assert "multi-to-one" in result.conflict_summary.lower()
        assert "RECOMMENDED ACTIONS" in result.recommended_action

    def test_degraded_no_aggregation_data(
        self,
        test_request_id: str,
    ) -> None:
        """Test degraded response doesn't contain aggregated values."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MAPPING_MISSING,
            conflict_details={},
            severity="critical",
        )

        # Act
        result = create_degraded_response(
            conflict=conflict,
            available_mappings=None,
            request_id=test_request_id,
        )

        # Assert: Degraded result should not have aggregated values
        # It only shows available sources (which is empty here)
        assert result.available_sources == []
        assert "Cannot aggregate" in result.conflict_summary


# Tests for resolution strategy
class TestResolveConflictStrategy:
    """Test conflict resolution strategy selection."""

    def test_no_conflicts_allows_normal_operation(self) -> None:
        """Test no conflicts allows normal operation."""
        # Act
        strategy = resolve_conflict_strategy([])

        # Assert
        assert strategy == ConflictResolutionStrategy.REJECT  # Safe default

    def test_critical_conflict_requires_reject(self) -> None:
        """Test critical conflict requires reject strategy."""
        # Arrange
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MULTI_TO_ONE,
                conflict_details={},
                severity="critical",
            ),
        ]

        # Act
        strategy = resolve_conflict_strategy(conflicts)

        # Assert
        assert strategy == ConflictResolutionStrategy.REJECT

    def test_warning_may_allow_degrade(self) -> None:
        """Test warning conflicts may allow degradation."""
        # Arrange
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.CROSS_SYSTEM,
                conflict_details={},
                severity="warning",
            ),
        ]

        # Act
        strategy = resolve_conflict_strategy(
            conflicts,
            auto_resolve_config={"allow_degrade": True},
        )

        # Assert
        assert strategy == ConflictResolutionStrategy.DEGRADE

    def test_multi_to_one_always_reject(self) -> None:
        """Test multi-to-one always requires reject even with degrade config."""
        # Arrange
        conflicts = [
            ConflictDetectionResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MULTI_TO_ONE,
                conflict_details={},
                severity="warning",  # Even with warning severity
            ),
        ]

        # Act
        strategy = resolve_conflict_strategy(
            conflicts,
            auto_resolve_config={"allow_degrade": True},
        )

        # Assert
        assert strategy == ConflictResolutionStrategy.REJECT


# Tests for should_degrade
class TestShouldDegrade:
    """Test degradation eligibility."""

    def test_critical_never_degrades(self) -> None:
        """Test critical conflicts never degrade."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.CROSS_SYSTEM,
            conflict_details={},
            severity="critical",
        )

        # Act & Assert
        assert should_degrade(conflict) is False

    def test_multi_to_one_never_degrades(self) -> None:
        """Test multi-to-one never degrades."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MULTI_TO_ONE,
            conflict_details={},
            severity="warning",
        )

        # Act & Assert
        assert should_degrade(conflict) is False

    def test_missing_mapping_never_degrades(self) -> None:
        """Test missing mapping never degrades."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MAPPING_MISSING,
            conflict_details={},
            severity="warning",
        )

        # Act & Assert
        assert should_degrade(conflict) is False

    def test_cross_system_warning_may_degrade(self) -> None:
        """Test cross-system warning may degrade."""
        # Arrange
        conflict = ConflictDetectionResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.CROSS_SYSTEM,
            conflict_details={},
            severity="warning",
        )

        # Act & Assert
        assert should_degrade(conflict) is True


# Tests for merge_degraded_results
class TestMergeDegradedResults:
    """Test merging multiple degraded results."""

    def test_merge_single_result(self, test_request_id: str) -> None:
        """Test merging single result returns itself."""
        # Arrange
        result = DegradedResult(
            unified_id="EQUIP-001",
            entity_type=EntityType.EQUIPMENT,
            conflict_type=ConflictType.MULTI_TO_ONE,
            available_sources=[{"source_system": "ERP", "source_id": "ERP-001"}],
            conflict_summary="Conflict for EQUIP-001",
            recommended_action="Review mapping",
            request_id=test_request_id,
        )

        # Act
        merged = merge_degraded_results([result])

        # Assert
        assert merged.unified_id == "EQUIP-001"
        assert len(merged.available_sources) == 1

    def test_merge_multiple_results(self, test_request_id: str) -> None:
        """Test merging multiple degraded results."""
        # Arrange
        results = [
            DegradedResult(
                unified_id="EQUIP-001",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.MULTI_TO_ONE,
                available_sources=[{"source_system": "ERP", "source_id": "ERP-001"}],
                conflict_summary="Conflict 1",
                recommended_action="Review 1",
                request_id=test_request_id,
            ),
            DegradedResult(
                unified_id="EQUIP-002",
                entity_type=EntityType.EQUIPMENT,
                conflict_type=ConflictType.CROSS_SYSTEM,
                available_sources=[{"source_system": "MES", "source_id": "MES-002"}],
                conflict_summary="Conflict 2",
                recommended_action="Review 2",
                request_id=test_request_id,
            ),
        ]

        # Act
        merged = merge_degraded_results(results)

        # Assert
        assert len(merged.available_sources) == 2
        assert "Multiple mapping conflicts" in merged.conflict_summary

    def test_merge_empty_raises(self) -> None:
        """Test merging empty list raises error."""
        # Act & Assert
        with pytest.raises(ValueError, match="Cannot merge empty list"):
            merge_degraded_results([])
