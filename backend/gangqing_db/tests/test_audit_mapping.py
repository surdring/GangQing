"""Unit tests for audit mapping module.

Tests the AuditMappingEvent model and AuditMappingLogger class.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from pydantic import ValidationError

from gangqing_db.audit_mapping import (
    AuditMappingEvent,
    AuditMappingLogger,
    MappingAuditEventType,
    build_mapping_audit_event,
    create_audit_mapping_logger,
)
from gangqing.common.context import RequestContext
from gangqing.semantic.models import EntityType


class TestMappingAuditEventType:
    """Tests for MappingAuditEventType enum."""

    def test_event_type_values(self) -> None:
        """Test that all event types have correct string values."""
        assert MappingAuditEventType.MAPPING_QUERY.value == "mapping.query"
        assert MappingAuditEventType.MAPPING_CONFLICT_DETECTED.value == "mapping.conflict_detected"
        assert MappingAuditEventType.MAPPING_AGGREGATION_BLOCKED.value == "mapping.aggregation_blocked"
        assert MappingAuditEventType.MAPPING_VERSION_CREATED.value == "mapping.version_created"
        assert MappingAuditEventType.MAPPING_VERSION_UPDATED.value == "mapping.version_updated"
        assert MappingAuditEventType.MAPPING_VERSION_DELETED.value == "mapping.version_deleted"


class TestAuditMappingEvent:
    """Tests for AuditMappingEvent model."""

    def test_audit_event_creation(self) -> None:
        """Test basic AuditMappingEvent creation."""
        event = AuditMappingEvent(
            event_type="mapping.query",
            unified_id="equipment-001",
            entity_type="equipment",
            tenant_id="tenant-001",
            project_id="project-001",
            request_id="req-123",
            user_id="user-001",
        )

        assert event.event_type == "mapping.query"
        assert event.unified_id == "equipment-001"
        assert event.entity_type == "equipment"
        assert event.tenant_id == "tenant-001"
        assert event.project_id == "project-001"
        assert event.request_id == "req-123"
        assert event.user_id == "user-001"
        assert event.timestamp is not None

    def test_audit_event_with_extended_fields(self) -> None:
        """Test AuditMappingEvent with extended T56.4 fields."""
        event = AuditMappingEvent(
            event_type="mapping.query",
            unified_id="mat-001",
            entity_type="material",
            tenant_id="t1",
            project_id="p1",
            request_id="r1",
            version=3,
            result_count=1,
            conflict_type="multi_to_one",
            severity="critical",
            block_reason="Aggregation blocked due to conflicts",
            entity_refs=[{"unified_id": "mat-001", "entity_type": "material"}],
            result_status="blocked",
            error_code="AGGREGATION_BLOCKED",
            details={"extra": "info"},
        )

        assert event.version == 3
        assert event.result_count == 1
        assert event.conflict_type == "multi_to_one"
        assert event.severity == "critical"
        assert event.block_reason == "Aggregation blocked due to conflicts"
        assert event.entity_refs is not None
        assert event.result_status == "blocked"
        assert event.error_code == "AGGREGATION_BLOCKED"

    def test_block_reason_english_validation(self) -> None:
        """Test that block reason must be in English."""
        # Valid English reason
        event = AuditMappingEvent(
            event_type="mapping.aggregation_blocked",
            unified_id="u1",
            entity_type="equipment",
            tenant_id="t1",
            project_id="p1",
            request_id="r1",
            block_reason="Valid English reason",
        )
        assert event.block_reason == "Valid English reason"


class TestBuildMappingAuditEvent:
    """Tests for build_mapping_audit_event helper."""

    def test_build_event_from_context(self) -> None:
        """Test building event from RequestContext."""
        ctx = MagicMock(spec=RequestContext)
        ctx.tenant_id = "tenant-123"
        ctx.project_id = "project-456"
        ctx.user_id = "user-789"
        ctx.request_id = "req-abc"

        event = build_mapping_audit_event(
            event_type="mapping.create",
            unified_id="equip-001",
            entity_type=EntityType.EQUIPMENT,
            ctx=ctx,
            version=1,
            details={"source_system": "ERP"},
        )

        assert event.event_type == "mapping.create"
        assert event.unified_id == "equip-001"
        assert event.entity_type == "equipment"
        assert event.tenant_id == "tenant-123"
        assert event.project_id == "project-456"
        assert event.user_id == "user-789"
        assert event.request_id == "req-abc"
        assert event.version == 1
        assert event.details == {"source_system": "ERP"}


class TestAuditMappingLogger:
    """Tests for AuditMappingLogger class."""

    @pytest.fixture
    def mock_context(self) -> Any:
        """Create mock request context."""
        ctx = MagicMock()
        ctx.request_id = "req-test-123"
        ctx.tenant_id = "tenant-001"
        ctx.project_id = "project-001"
        ctx.user_id = "user-123"
        ctx.session_id = "session-456"
        return ctx

    @pytest.fixture
    def mock_audit_fn(self) -> Any:
        """Create mock audit log function."""
        return MagicMock()

    @pytest.fixture
    def logger(self, mock_context: Any, mock_audit_fn: Any) -> AuditMappingLogger:
        """Create audit mapping logger."""
        return AuditMappingLogger(mock_context, mock_audit_fn)

    def test_logger_initialization(self, mock_context: Any) -> None:
        """Test logger initialization."""
        logger = AuditMappingLogger(mock_context)
        assert logger.ctx == mock_context

    def test_log_mapping_query_success(self, logger: AuditMappingLogger, mock_audit_fn: Any) -> None:
        """Test logging successful mapping query."""
        with patch("gangqing_db.audit_log.insert_audit_log_event") as mock_insert:
            event = logger.log_mapping_query(
                unified_id="equip-001",
                entity_type="equipment",
                version=2,
                result_count=1,
                found=True,
                details={"cache_hit": True},
            )

            assert event.event_type == "mapping.query"
            assert event.unified_id == "equip-001"
            assert event.entity_type == "equipment"
            assert event.version == 2
            assert event.result_count == 1
            assert event.result_status == "success"
            assert event.details["found"] is True
            assert event.details["cache_hit"] is True

    def test_log_mapping_query_not_found(self, logger: AuditMappingLogger) -> None:
        """Test logging mapping query with not found result."""
        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            event = logger.log_mapping_query(
                unified_id="missing-001",
                entity_type="material",
                version=None,
                result_count=0,
                found=False,
            )

            assert event.result_status == "failure"
            assert event.error_code == "NOT_FOUND"

    def test_log_conflict_detected(self, logger: AuditMappingLogger) -> None:
        """Test logging conflict detection."""
        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            event = logger.log_conflict_detected(
                unified_id="conflict-001",
                entity_type="equipment",
                conflict_type="multi_to_one",
                severity="critical",
                conflict_details={
                    "mapping_count": 2,
                    "source_systems": ["ERP", "MES"],
                },
            )

            assert event.event_type == "mapping.conflict_detected"
            assert event.conflict_type == "multi_to_one"
            assert event.severity == "critical"
            assert event.result_status == "detected"
            assert event.details["mapping_count"] == 2

    def test_log_aggregation_blocked(self, logger: AuditMappingLogger) -> None:
        """Test logging aggregation blocked event."""
        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            event = logger.log_aggregation_blocked(
                reason="Multiple mappings detected for entity",
                unified_id="block-001",
                entity_type="batch",
                entity_refs=[{"unified_id": "block-001", "entity_type": "batch"}],
                conflict_count=2,
                conflict_types=["multi_to_one", "cross_system"],
                error_code="AGGREGATION_BLOCKED",
            )

            assert event.event_type == "mapping.aggregation_blocked"
            assert event.block_reason == "Multiple mappings detected for entity"
            assert event.result_status == "blocked"
            assert event.error_code == "AGGREGATION_BLOCKED"
            assert event.details["conflict_count"] == 2

    def test_log_version_created(self, logger: AuditMappingLogger) -> None:
        """Test logging version created event."""
        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            event = logger.log_version_created(
                unified_id="new-001",
                entity_type="order",
                version=1,
                source_system="ERP",
                source_id="erp-new-001",
                details={"created_by": "admin"},
            )

            assert event.event_type == "mapping.version_created"
            assert event.version == 1
            assert event.result_status == "success"
            assert event.details["source_system"] == "ERP"
            assert event.details["source_id"] == "erp-new-001"

    def test_log_version_updated(self, logger: AuditMappingLogger) -> None:
        """Test logging version updated event."""
        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            event = logger.log_version_updated(
                unified_id="update-001",
                entity_type="material",
                new_version=3,
                old_version=2,
                source_system_changed=True,
                source_id_changed=False,
            )

            assert event.event_type == "mapping.version_updated"
            assert event.version == 3
            assert event.details["old_version"] == 2
            assert event.details["new_version"] == 3
            assert event.details["source_system_changed"] is True
            assert event.details["source_id_changed"] is False

    def test_log_version_deleted(self, logger: AuditMappingLogger) -> None:
        """Test logging version deleted event."""
        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            event = logger.log_version_deleted(
                unified_id="delete-001",
                entity_type="equipment",
                version=2,
                soft_delete=True,
                details={"deleted_by": "admin"},
            )

            assert event.event_type == "mapping.version_deleted"
            assert event.version == 2
            assert event.result_status == "success"
            assert event.details["soft_delete"] is True

    def test_request_id_tracing(self, mock_context: Any) -> None:
        """Test that request_id is traced through all events."""
        mock_context.request_id = "trace-123"
        logger = AuditMappingLogger(mock_context)

        with patch("gangqing_db.audit_log.insert_audit_log_event"):
            # Test various event types
            query_event = logger.log_mapping_query("u1", "equipment")
            assert query_event.request_id == "trace-123"

            conflict_event = logger.log_conflict_detected("u2", "material", "type")
            assert conflict_event.request_id == "trace-123"

            block_event = logger.log_aggregation_blocked("reason")
            assert block_event.request_id == "trace-123"


class TestCreateAuditMappingLogger:
    """Tests for factory function."""

    def test_factory_function(self) -> None:
        """Test create_audit_mapping_logger factory."""
        ctx = MagicMock(spec=RequestContext)
        ctx.tenant_id = "t1"
        ctx.project_id = "p1"
        ctx.request_id = "r1"

        logger = create_audit_mapping_logger(ctx)

        assert isinstance(logger, AuditMappingLogger)
        assert logger.ctx == ctx

    def test_factory_with_audit_fn(self) -> None:
        """Test factory with custom audit function."""
        ctx = MagicMock()
        mock_fn = MagicMock()

        logger = create_audit_mapping_logger(ctx, mock_fn)

        assert logger._audit_log_fn == mock_fn


class TestAuditMappingIntegration:
    """Integration tests for audit mapping."""

    def test_event_serialization(self) -> None:
        """Test that events can be serialized for audit log."""
        event = AuditMappingEvent(
            event_type="mapping.query",
            unified_id="test-001",
            entity_type="equipment",
            tenant_id="t1",
            project_id="p1",
            request_id="r1",
            version=5,
            result_count=1,
            conflict_type=None,
            severity=None,
        )

        # Test model_dump for serialization
        data = event.model_dump(
            include={
                "unified_id",
                "entity_type",
                "version",
                "result_count",
                "conflict_type",
            },
            exclude_none=True,
        )

        assert "unified_id" in data
        assert "entity_type" in data
        assert "version" in data
        assert "result_count" in data
        # None values should be excluded
        assert "conflict_type" not in data

    def test_all_event_types_covered(self) -> None:
        """Test that all required event types from T56.4 are covered."""
        required_types = {
            "mapping.query",
            "mapping.conflict_detected",
            "mapping.aggregation_blocked",
            "mapping.version_created",
            "mapping.version_updated",
            "mapping.version_deleted",
        }

        available_types = {t.value for t in MappingAuditEventType}

        assert required_types <= available_types
