"""Unit tests for semantic layer mapping versioning module."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from sqlalchemy import create_engine, text

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import Role, _ROLE_TO_CAPABILITIES
from gangqing.semantic.mapping_versioning import MappingVersionManager
from gangqing.semantic.models import (
    EntityMappingCreate,
    EntityMappingUpdate,
    EntityType,
    MAPPING_READ_CAPABILITY,
    MAPPING_WRITE_CAPABILITY,
)
from gangqing_db.settings import load_settings


# Ensure test database URL is set
@pytest.fixture(scope="module")
def db_engine():
    """Create database engine for tests."""
    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    yield engine


@pytest.fixture
def test_tenant_id() -> str:
    """Generate unique test tenant ID."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_project_id() -> str:
    """Generate unique test project ID."""
    return f"test-project-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def admin_ctx(test_tenant_id: str, test_project_id: str) -> RequestContext:
    """Create admin request context with full permissions."""
    return RequestContext(
        request_id=f"req-test-{uuid.uuid4().hex[:8]}",
        tenant_id=test_tenant_id,
        project_id=test_project_id,
        user_id="test-admin",
        role=Role.ADMIN.value,
    )


@pytest.fixture
def read_only_ctx(test_tenant_id: str, test_project_id: str) -> RequestContext:
    """Create read-only request context (dispatcher role has no write permission)."""
    return RequestContext(
        request_id=f"req-test-{uuid.uuid4().hex[:8]}",
        tenant_id=test_tenant_id,
        project_id=test_project_id,
        user_id="test-dispatcher",
        role=Role.DISPATCHER.value,
    )


@pytest.fixture
def cross_tenant_ctx(test_tenant_id: str, test_project_id: str) -> RequestContext:
    """Create context with different tenant for isolation testing."""
    return RequestContext(
        request_id=f"req-test-{uuid.uuid4().hex[:8]}",
        tenant_id="other-tenant",
        project_id=test_project_id,
        user_id="test-user",
        role=Role.ADMIN.value,
    )


@pytest.fixture(autouse=True)
def cleanup_test_data(db_engine, test_tenant_id: str, test_project_id: str):
    """Clean up test data after each test."""
    yield
    # Cleanup after test
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM entity_mappings WHERE tenant_id = :tenant_id"),
            {"tenant_id": test_tenant_id},
        )


class TestEntityMappingSchema:
    """Tests for Pydantic schema validation."""

    def test_entity_type_enum_values(self):
        """Test EntityType enum has expected values."""
        assert EntityType.EQUIPMENT.value == "equipment"
        assert EntityType.MATERIAL.value == "material"
        assert EntityType.BATCH.value == "batch"
        assert EntityType.ORDER.value == "order"

    def test_entity_mapping_create_validation(self):
        """Test EntityMappingCreate model validation."""
        mapping = EntityMappingCreate(
            unified_id="EQ-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-001",
            tenant_id="test-tenant",
            project_id="test-project",
        )
        assert mapping.unified_id == "EQ-001"
        assert mapping.entity_type == EntityType.EQUIPMENT
        assert mapping.source_system == "MES"

    def test_entity_mapping_create_min_length_validation(self):
        """Test unified_id must not be empty."""
        with pytest.raises(Exception):  # Pydantic validation error
            EntityMappingCreate(
                unified_id="",
                entity_type=EntityType.EQUIPMENT,
                source_system="MES",
                source_id="MES-EQ-001",
                tenant_id="test-tenant",
                project_id="test-project",
            )

    def test_entity_mapping_update_validation(self):
        """Test EntityMappingUpdate requires at least one field."""
        with pytest.raises(Exception):  # Pydantic validation error
            EntityMappingUpdate()  # No fields provided

    def test_entity_mapping_update_partial(self):
        """Test EntityMappingUpdate with partial fields."""
        update = EntityMappingUpdate(source_system="ERP")
        assert update.source_system == "ERP"
        assert update.source_id is None


class TestMappingVersionManagerCreate:
    """Tests for MappingVersionManager.create_mapping."""

    def test_create_mapping_success(self, admin_ctx: RequestContext):
        """Test successful mapping creation with version 1."""
        manager = MappingVersionManager(admin_ctx)
        create_data = EntityMappingCreate(
            unified_id="EQ-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-001",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )

        result = manager.create_mapping(create_data)

        assert result.unified_id == "EQ-001"
        assert result.entity_type == EntityType.EQUIPMENT
        assert result.source_system == "MES"
        assert result.source_id == "MES-EQ-001"
        assert result.version == 1
        assert result.valid_to is None  # Current version
        assert result.tenant_id == admin_ctx.tenant_id
        assert result.project_id == admin_ctx.project_id

    def test_create_mapping_cross_tenant_rejected(self, admin_ctx: RequestContext):
        """Test cross-tenant creation is rejected with AUTH_ERROR."""
        manager = MappingVersionManager(admin_ctx)
        create_data = EntityMappingCreate(
            unified_id="EQ-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-001",
            tenant_id="different-tenant",  # Different from context
            project_id=admin_ctx.project_id,
        )

        with pytest.raises(AppError) as exc_info:
            manager.create_mapping(create_data)

        assert exc_info.value.code == ErrorCode.AUTH_ERROR

    def test_create_mapping_cross_project_rejected(self, admin_ctx: RequestContext):
        """Test cross-project creation is rejected with AUTH_ERROR."""
        manager = MappingVersionManager(admin_ctx)
        create_data = EntityMappingCreate(
            unified_id="EQ-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-001",
            tenant_id=admin_ctx.tenant_id,
            project_id="different-project",  # Different from context
        )

        with pytest.raises(AppError) as exc_info:
            manager.create_mapping(create_data)

        assert exc_info.value.code == ErrorCode.AUTH_ERROR

    def test_create_mapping_forbidden(self, read_only_ctx: RequestContext):
        """Test mapping creation without write permission returns FORBIDDEN."""
        manager = MappingVersionManager(read_only_ctx)
        create_data = EntityMappingCreate(
            unified_id="EQ-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-001",
            tenant_id=read_only_ctx.tenant_id,
            project_id=read_only_ctx.project_id,
        )

        with pytest.raises(AppError) as exc_info:
            manager.create_mapping(create_data)

        assert exc_info.value.code == ErrorCode.FORBIDDEN


class TestMappingVersionManagerUpdate:
    """Tests for MappingVersionManager.update_mapping."""

    def test_update_creates_new_version(self, admin_ctx: RequestContext):
        """Test update creates new version and marks old as expired."""
        manager = MappingVersionManager(admin_ctx)

        # Create initial mapping
        create_data = EntityMappingCreate(
            unified_id="EQ-002",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-002",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        initial = manager.create_mapping(create_data)
        assert initial.version == 1
        assert initial.valid_to is None

        # Update mapping
        update_data = EntityMappingUpdate(source_system="ERP", source_id="ERP-EQ-002")
        updated = manager.update_mapping("EQ-002", EntityType.EQUIPMENT, update_data)

        assert updated.version == 2
        assert updated.source_system == "ERP"
        assert updated.source_id == "ERP-EQ-002"
        assert updated.valid_to is None

        # Verify old version is expired
        history = manager.get_mapping_history("EQ-002", EntityType.EQUIPMENT)
        assert len(history) == 2

        # Find version 1 in history and verify it's expired
        v1 = next(h for h in history if h.version == 1)
        assert v1.valid_to is not None

    def test_update_mapping_not_found(self, admin_ctx: RequestContext):
        """Test updating non-existent mapping returns NOT_FOUND."""
        manager = MappingVersionManager(admin_ctx)
        update_data = EntityMappingUpdate(source_system="ERP")

        with pytest.raises(AppError) as exc_info:
            manager.update_mapping("NON-EXISTENT", EntityType.EQUIPMENT, update_data)

        assert exc_info.value.code == ErrorCode.NOT_FOUND

    def test_update_metadata_merge(self, admin_ctx: RequestContext):
        """Test metadata is merged on update."""
        manager = MappingVersionManager(admin_ctx)

        # Create with initial metadata
        create_data = EntityMappingCreate(
            unified_id="EQ-003",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-003",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
            metadata={"line": "A1", "area": "casting"},
        )
        initial = manager.create_mapping(create_data)
        assert initial.metadata == {"line": "A1", "area": "casting"}

        # Update with new metadata
        update_data = EntityMappingUpdate(metadata={"status": "active"})
        updated = manager.update_mapping("EQ-003", EntityType.EQUIPMENT, update_data)

        # Metadata should be merged
        assert updated.metadata["line"] == "A1"
        assert updated.metadata["area"] == "casting"
        assert updated.metadata["status"] == "active"


class TestMappingVersionManagerQuery:
    """Tests for MappingVersionManager query operations."""

    def test_get_current_mapping_found(self, admin_ctx: RequestContext):
        """Test get_current_mapping returns mapping when found."""
        manager = MappingVersionManager(admin_ctx)

        create_data = EntityMappingCreate(
            unified_id="EQ-004",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-004",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        created = manager.create_mapping(create_data)

        result = manager.get_current_mapping("EQ-004", EntityType.EQUIPMENT)

        assert result is not None
        assert result.unified_id == "EQ-004"
        assert result.entity_type == EntityType.EQUIPMENT
        assert result.version == 1

    def test_get_current_mapping_not_found(self, admin_ctx: RequestContext):
        """Test get_current_mapping returns None when not found."""
        manager = MappingVersionManager(admin_ctx)

        result = manager.get_current_mapping("NON-EXISTENT", EntityType.EQUIPMENT)

        assert result is None

    def test_get_mapping_history_ordered(self, admin_ctx: RequestContext):
        """Test get_mapping_history returns versions ordered by version desc."""
        manager = MappingVersionManager(admin_ctx)

        # Create and update mapping to get multiple versions
        create_data = EntityMappingCreate(
            unified_id="EQ-005",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-005",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        manager.create_mapping(create_data)

        # Update twice to create 3 versions total
        for i in range(2):
            update = EntityMappingUpdate(source_id=f"MES-EQ-005-v{i+2}")
            manager.update_mapping("EQ-005", EntityType.EQUIPMENT, update)

        history = manager.get_mapping_history("EQ-005", EntityType.EQUIPMENT)

        assert len(history) == 3
        # Verify descending order
        assert history[0].version == 3
        assert history[1].version == 2
        assert history[2].version == 1

    def test_get_mapping_history_empty(self, admin_ctx: RequestContext):
        """Test get_mapping_history returns empty list when no mappings."""
        manager = MappingVersionManager(admin_ctx)

        history = manager.get_mapping_history("NON-EXISTENT", EntityType.EQUIPMENT)

        assert history == []


class TestMappingVersionManagerDelete:
    """Tests for MappingVersionManager.soft_delete_mapping."""

    def test_soft_delete_success(self, admin_ctx: RequestContext):
        """Test soft delete marks mapping as expired."""
        manager = MappingVersionManager(admin_ctx)

        create_data = EntityMappingCreate(
            unified_id="EQ-006",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-006",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        manager.create_mapping(create_data)

        # Soft delete
        result = manager.soft_delete_mapping("EQ-006", EntityType.EQUIPMENT)
        assert result is True

        # Verify mapping is no longer current
        current = manager.get_current_mapping("EQ-006", EntityType.EQUIPMENT)
        assert current is None

        # Verify history still exists with expired version
        history = manager.get_mapping_history("EQ-006", EntityType.EQUIPMENT)
        assert len(history) == 1
        assert history[0].valid_to is not None

    def test_soft_delete_not_found(self, admin_ctx: RequestContext):
        """Test soft delete returns False when mapping not found."""
        manager = MappingVersionManager(admin_ctx)

        result = manager.soft_delete_mapping("NON-EXISTENT", EntityType.EQUIPMENT)

        assert result is False

    def test_soft_delete_forbidden(self, read_only_ctx: RequestContext):
        """Test soft delete without write permission returns FORBIDDEN."""
        manager = MappingVersionManager(read_only_ctx)

        with pytest.raises(AppError) as exc_info:
            manager.soft_delete_mapping("EQ-001", EntityType.EQUIPMENT)

        assert exc_info.value.code == ErrorCode.FORBIDDEN


class TestMappingVersionManagerConflict:
    """Tests for version conflict detection."""

    def test_check_version_conflict_no_conflict(self, admin_ctx: RequestContext):
        """Test check_version_conflict returns no conflict when versions match."""
        manager = MappingVersionManager(admin_ctx)

        create_data = EntityMappingCreate(
            unified_id="EQ-007",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-007",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        manager.create_mapping(create_data)

        has_conflict, actual_version = manager.check_version_conflict(
            "EQ-007", EntityType.EQUIPMENT, expected_version=1
        )

        assert has_conflict is False
        assert actual_version == 1

    def test_check_version_conflict_detected(self, admin_ctx: RequestContext):
        """Test check_version_conflict detects version mismatch."""
        manager = MappingVersionManager(admin_ctx)

        create_data = EntityMappingCreate(
            unified_id="EQ-008",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-008",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        manager.create_mapping(create_data)

        # Update to create version 2
        update = EntityMappingUpdate(source_id="MES-EQ-008-v2")
        manager.update_mapping("EQ-008", EntityType.EQUIPMENT, update)

        # Check with outdated expected version
        has_conflict, actual_version = manager.check_version_conflict(
            "EQ-008", EntityType.EQUIPMENT, expected_version=1
        )

        assert has_conflict is True
        assert actual_version == 2

    def test_check_version_conflict_not_found(self, admin_ctx: RequestContext):
        """Test check_version_conflict returns conflict when mapping not found."""
        manager = MappingVersionManager(admin_ctx)

        has_conflict, actual_version = manager.check_version_conflict(
            "NON-EXISTENT", EntityType.EQUIPMENT, expected_version=1
        )

        assert has_conflict is True
        assert actual_version is None


class TestTenantIsolation:
    """Tests for tenant and project isolation."""

    def test_cross_tenant_query_not_visible(self, admin_ctx: RequestContext, cross_tenant_ctx: RequestContext):
        """Test mappings from other tenant are not visible."""
        # Create mapping with admin context
        manager1 = MappingVersionManager(admin_ctx)
        create_data = EntityMappingCreate(
            unified_id="EQ-ISO-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="MES",
            source_id="MES-EQ-ISO-001",
            tenant_id=admin_ctx.tenant_id,
            project_id=admin_ctx.project_id,
        )
        manager1.create_mapping(create_data)

        # Try to query with different tenant context
        manager2 = MappingVersionManager(cross_tenant_ctx)
        result = manager2.get_current_mapping("EQ-ISO-001", EntityType.EQUIPMENT)

        # Should not find the mapping (different tenant)
        assert result is None

    def test_all_entity_types_supported(self, admin_ctx: RequestContext):
        """Test all entity types can be created and queried."""
        manager = MappingVersionManager(admin_ctx)

        entity_types = [
            (EntityType.EQUIPMENT, "EQ-009"),
            (EntityType.MATERIAL, "MAT-001"),
            (EntityType.BATCH, "BATCH-001"),
            (EntityType.ORDER, "ORD-001"),
        ]

        for entity_type, unified_id in entity_types:
            create_data = EntityMappingCreate(
                unified_id=unified_id,
                entity_type=entity_type,
                source_system="MES",
                source_id=f"MES-{unified_id}",
                tenant_id=admin_ctx.tenant_id,
                project_id=admin_ctx.project_id,
            )
            result = manager.create_mapping(create_data)

            assert result.entity_type == entity_type
            assert result.unified_id == unified_id


class TestCapabilityConstants:
    """Tests for RBAC capability constants."""

    def test_mapping_capabilities_exist(self):
        """Test mapping capability constants are properly defined."""
        from gangqing.semantic.models import (
            MAPPING_READ_CAPABILITY,
            MAPPING_WRITE_CAPABILITY,
            MAPPING_CONFLICT_READ_CAPABILITY,
        )

        assert MAPPING_READ_CAPABILITY == "semantic:mapping:read"
        assert MAPPING_WRITE_CAPABILITY == "semantic:mapping:write"
        assert MAPPING_CONFLICT_READ_CAPABILITY == "semantic:mapping:conflict:read"

    def test_admin_has_mapping_capabilities(self):
        """Test admin role has mapping capabilities."""
        admin_caps = _ROLE_TO_CAPABILITIES.get(Role.ADMIN, set())
        assert MAPPING_READ_CAPABILITY in admin_caps
        assert MAPPING_WRITE_CAPABILITY in admin_caps
