"""Entity mapping versioning management module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import create_engine, text
import structlog

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import assert_has_capability
from gangqing.semantic.mapping_evidence import (
    MappingEvidenceBuilder,
    create_mapping_evidence_builder,
)
from gangqing.semantic.models import (
    EntityMappingCreate,
    EntityMappingResponse,
    EntityMappingUpdate,
    EntityType,
    MappingVersionHistory,
    MAPPING_READ_CAPABILITY,
    MAPPING_WRITE_CAPABILITY,
)
from gangqing_db.audit_mapping import (
    AuditMappingLogger,
    create_audit_mapping_logger,
)
from gangqing_db.audit_log import insert_audit_log_event
from gangqing_db.settings import load_settings


logger = structlog.get_logger(__name__)


def _get_engine():
    """Get database engine from settings."""
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


class MappingVersionManager:
    """Manager class for entity mapping versioning operations.

    Provides CRUD operations with version control:
    - Create new mapping (version starts from 1)
    - Update mapping (creates new version, marks old as expired)
    - Get current mapping (valid_to IS NULL)
    - Get mapping history (all versions ordered by version desc)
    - Soft delete (mark current version as expired)

    All operations enforce:
    - RBAC permission checks
    - Tenant/project isolation
    - Audit logging
    """

    def __init__(self, ctx: RequestContext) -> None:
        """Initialize with request context for isolation and audit.

        Args:
            ctx: RequestContext with tenant_id, project_id, request_id, user info
        """
        self.ctx = ctx
        self._engine = _get_engine()
        # Initialize evidence builder for mapping operations
        self._evidence_builder = create_mapping_evidence_builder(ctx)
        # Initialize audit mapping logger
        self._audit_logger = create_audit_mapping_logger(ctx, insert_audit_log_event)

    def _require_read_permission(self) -> None:
        """Check read permission and audit if denied."""
        try:
            role = self.ctx.role or ""
            assert_has_capability(
                ctx=self.ctx,
                role_raw=role,
                capability=MAPPING_READ_CAPABILITY,
            )
        except AppError as e:
            if e.code == ErrorCode.FORBIDDEN:
                write_audit_event(
                    ctx=self.ctx,
                    event_type=AuditEventType.RBAC_DENIED.value,
                    resource="semantic:mapping",
                    action_summary={
                        "capability": MAPPING_READ_CAPABILITY,
                        "role": self.ctx.role,
                        "operation": "read",
                    },
                    result_status="failure",
                    error_code=e.code.value,
                )
            raise

    def _require_write_permission(self) -> None:
        """Check write permission and audit if denied."""
        try:
            role = self.ctx.role or ""
            assert_has_capability(
                ctx=self.ctx,
                role_raw=role,
                capability=MAPPING_WRITE_CAPABILITY,
            )
        except AppError as e:
            if e.code == ErrorCode.FORBIDDEN:
                write_audit_event(
                    ctx=self.ctx,
                    event_type=AuditEventType.RBAC_DENIED.value,
                    resource="semantic:mapping",
                    action_summary={
                        "capability": MAPPING_WRITE_CAPABILITY,
                        "role": self.ctx.role,
                        "operation": "write",
                    },
                    result_status="failure",
                    error_code=e.code.value,
                )
            raise

    def _audit_mapping_event(
        self,
        event_type: str,
        unified_id: str,
        entity_type: EntityType,
        version: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        result_status: str = "success",
        error_code: Optional[str] = None,
    ) -> None:
        """Write mapping audit event."""
        action_summary = {
            "unified_id": unified_id,
            "entity_type": entity_type.value,
        }
        if version is not None:
            action_summary["version"] = version
        if details:
            action_summary.update(details)

        write_audit_event(
            ctx=self.ctx,
            event_type=event_type,
            resource=f"semantic:mapping:{entity_type.value}:{unified_id}",
            action_summary=action_summary,
            result_status=result_status,
            error_code=error_code,
        )

    def _row_to_response(self, row) -> EntityMappingResponse:
        """Convert database row to EntityMappingResponse."""
        return EntityMappingResponse(
            unified_id=row.unified_id,
            entity_type=EntityType(row.entity_type),
            source_system=row.source_system,
            source_id=row.source_id,
            tenant_id=row.tenant_id,
            project_id=row.project_id,
            version=row.version,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            created_by=row.created_by,
            metadata=row.metadata,
        )

    def _row_to_history(self, row) -> MappingVersionHistory:
        """Convert database row to MappingVersionHistory."""
        return MappingVersionHistory(
            unified_id=row.unified_id,
            entity_type=EntityType(row.entity_type),
            version=row.version,
            source_system=row.source_system,
            source_id=row.source_id,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            created_by=row.created_by,
            tenant_id=row.tenant_id,
            project_id=row.project_id,
            metadata=row.metadata,
        )

    def create_mapping(
        self,
        mapping: EntityMappingCreate,
    ) -> EntityMappingResponse:
        """Create a new entity mapping with version 1.

        Args:
            mapping: EntityMappingCreate model with mapping details

        Returns:
            EntityMappingResponse with created mapping

        Raises:
            AppError: If permission denied or database error
        """
        self._require_write_permission()

        # Verify tenant/project isolation - only create in current context
        if mapping.tenant_id != self.ctx.tenant_id:
            raise AppError(
                code=ErrorCode.AUTH_ERROR,
                message="Cross-tenant mapping creation not allowed",
                request_id=self.ctx.request_id,
                details={
                    "expected_tenant": self.ctx.tenant_id,
                    "provided_tenant": mapping.tenant_id,
                },
                retryable=False,
            )

        if mapping.project_id != self.ctx.project_id:
            raise AppError(
                code=ErrorCode.AUTH_ERROR,
                message="Cross-project mapping creation not allowed",
                request_id=self.ctx.request_id,
                details={
                    "expected_project": self.ctx.project_id,
                    "provided_project": mapping.project_id,
                },
                retryable=False,
            )

        now = datetime.now(timezone.utc)

        with self._engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": self.ctx.project_id},
            )
            conn.commit()

            result = conn.execute(
                text(
                    """
                    INSERT INTO entity_mappings (
                        tenant_id, project_id, unified_id, entity_type,
                        source_system, source_id, version, valid_from,
                        valid_to, created_by, metadata, created_at
                    ) VALUES (
                        :tenant_id, :project_id, :unified_id, :entity_type,
                        :source_system, :source_id, 1, :valid_from,
                        NULL, :created_by, CAST(:metadata AS jsonb), :created_at
                    )
                    RETURNING *
                    """
                ),
                {
                    "tenant_id": mapping.tenant_id,
                    "project_id": mapping.project_id,
                    "unified_id": mapping.unified_id,
                    "entity_type": mapping.entity_type.value,
                    "source_system": mapping.source_system,
                    "source_id": mapping.source_id,
                    "valid_from": now,
                    "created_by": mapping.created_by or self.ctx.user_id,
                    "metadata": (
                        None
                        if mapping.metadata is None
                        else __import__("json").dumps(mapping.metadata)
                    ),
                    "created_at": now,
                },
            )
            row = result.fetchone()
            conn.commit()

        response = self._row_to_response(row)

        self._audit_mapping_event(
            event_type="mapping.create",
            unified_id=mapping.unified_id,
            entity_type=mapping.entity_type,
            version=1,
            details={
                "source_system": mapping.source_system,
                "source_id": mapping.source_id,
            },
        )

        logger.info(
            "mapping_created",
            unified_id=mapping.unified_id,
            entity_type=mapping.entity_type.value,
            version=1,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            request_id=self.ctx.request_id,
        )

        return response

    def update_mapping(
        self,
        unified_id: str,
        entity_type: EntityType,
        update: EntityMappingUpdate,
    ) -> EntityMappingResponse:
        """Update an existing mapping by creating a new version.

        The current version is marked as expired (valid_to = now),
        and a new version is created with incremented version number.

        Args:
            unified_id: Unified entity ID to update
            entity_type: Entity type
            update: EntityMappingUpdate with fields to update

        Returns:
            EntityMappingResponse with new version

        Raises:
            AppError: If mapping not found, permission denied, or version conflict
        """
        self._require_write_permission()

        now = datetime.now(timezone.utc)

        with self._engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": self.ctx.project_id},
            )

            # Get current version
            current_result = conn.execute(
                text(
                    """
                    SELECT * FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                      AND valid_to IS NULL
                    """
                ),
                {
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )
            current_row = current_result.fetchone()

            if current_row is None:
                raise AppError(
                    code=ErrorCode.NOT_FOUND,
                    message="Mapping not found or already deleted",
                    request_id=self.ctx.request_id,
                    details={
                        "unified_id": unified_id,
                        "entity_type": entity_type.value,
                    },
                    retryable=False,
                )

            old_version = current_row.version
            new_version = old_version + 1

            # Merge metadata if provided
            new_metadata = current_row.metadata or {}
            if update.metadata:
                new_metadata.update(update.metadata)

            # Mark current version as expired
            conn.execute(
                text(
                    """
                    UPDATE entity_mappings
                    SET valid_to = :now
                    WHERE id = :id
                    """
                ),
                {"now": now, "id": current_row.id},
            )

            # Create new version
            new_result = conn.execute(
                text(
                    """
                    INSERT INTO entity_mappings (
                        tenant_id, project_id, unified_id, entity_type,
                        source_system, source_id, version, valid_from,
                        valid_to, created_by, metadata, created_at
                    ) VALUES (
                        :tenant_id, :project_id, :unified_id, :entity_type,
                        :source_system, :source_id, :version, :valid_from,
                        NULL, :created_by, CAST(:metadata AS jsonb), :created_at
                    )
                    RETURNING *
                    """
                ),
                {
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                    "source_system": (
                        update.source_system
                        if update.source_system is not None
                        else current_row.source_system
                    ),
                    "source_id": (
                        update.source_id
                        if update.source_id is not None
                        else current_row.source_id
                    ),
                    "version": new_version,
                    "valid_from": now,
                    "created_by": update.updated_by or self.ctx.user_id,
                    "metadata": (
                        None
                        if new_metadata is None or len(new_metadata) == 0
                        else __import__("json").dumps(new_metadata)
                    ),
                    "created_at": now,
                },
            )
            new_row = new_result.fetchone()

        response = self._row_to_response(new_row)

        self._audit_mapping_event(
            event_type="mapping.update",
            unified_id=unified_id,
            entity_type=entity_type,
            version=new_version,
            details={
                "old_version": old_version,
                "new_version": new_version,
                "source_system_changed": (
                    update.source_system is not None
                    and update.source_system != current_row.source_system
                ),
                "source_id_changed": (
                    update.source_id is not None
                    and update.source_id != current_row.source_id
                ),
            },
        )

        logger.info(
            "mapping_updated",
            unified_id=unified_id,
            entity_type=entity_type.value,
            old_version=old_version,
            new_version=new_version,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            request_id=self.ctx.request_id,
        )

        return response

    def get_current_mapping(
        self,
        unified_id: str,
        entity_type: EntityType,
    ) -> Optional[EntityMappingResponse]:
        """Get the current valid mapping (valid_to IS NULL).

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type

        Returns:
            EntityMappingResponse if found, None otherwise
        """
        self._require_read_permission()

        with self._engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": self.ctx.project_id},
            )
            conn.commit()

            result = conn.execute(
                text(
                    """
                    SELECT * FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                      AND valid_to IS NULL
                    """
                ),
                {
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )
            row = result.fetchone()

        if row is None:
            self._audit_mapping_event(
                event_type="mapping.query",
                unified_id=unified_id,
                entity_type=entity_type,
                details={"result": "not_found"},
            )
            return None

        response = self._row_to_response(row)

        self._audit_mapping_event(
            event_type="mapping.query",
            unified_id=unified_id,
            entity_type=entity_type,
            version=response.version,
            details={"result": "found"},
        )

        # Log audit event with AuditMappingLogger
        self._audit_logger.log_mapping_query(
            unified_id=unified_id,
            entity_type=entity_type.value,
            version=response.version,
            result_count=1,
            found=True,
        )

        return response

    def get_current_mapping_with_evidence(
        self,
        unified_id: str,
        entity_type: EntityType,
    ) -> Tuple[Optional[EntityMappingResponse], Optional[Any]]:
        """Get current mapping and build evidence.

        This method returns both the mapping response and the associated
        MappingEvidence for evidence chain integration.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type

        Returns:
            Tuple of (mapping_response, evidence). Evidence is None if mapping not found.
        """
        mapping = self.get_current_mapping(unified_id, entity_type)

        if mapping is None:
            # Create evidence for missing mapping
            evidence = self._evidence_builder.from_gate_result(
                unified_id=unified_id,
                entity_type=entity_type,
                mapping=None,
                gate_passed=False,
                gate_block_reason="Mapping not found",
            )
            return None, evidence

        # Create evidence for found mapping
        evidence = self._evidence_builder.from_mapping_response(
            mapping,
            gate_passed=True,
            conflict_status="clean",
        )

        return mapping, evidence

    def get_all_mappings_with_evidence(
        self,
        unified_id: str,
        entity_type: EntityType,
    ) -> Tuple[List[EntityMappingResponse], Any]:
        """Get all mappings for unified_id and build evidence.

        This method returns both the list of mappings and the associated
        MappingEvidence for evidence chain integration. Useful for detecting
        conflicts (multi-to-one mappings).

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type

        Returns:
            Tuple of (mappings, evidence)
        """
        mappings = self.get_all_mappings_for_unified_id(
            unified_id=unified_id,
            entity_type=entity_type,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
        )

        # Build evidence from mapping list
        evidence = self._evidence_builder.from_mapping_list(
            unified_id=unified_id,
            entity_type=entity_type,
            mappings=mappings,
            gate_passed=len(mappings) <= 1,  # Block if multiple mappings
            gate_block_reason="Multiple mappings detected" if len(mappings) > 1 else None,
        )

        return mappings, evidence

    def get_mapping_history(
        self,
        unified_id: str,
        entity_type: EntityType,
    ) -> List[MappingVersionHistory]:
        """Get all versions of a mapping ordered by version descending.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type

        Returns:
            List of MappingVersionHistory ordered by version desc
        """
        self._require_read_permission()

        with self._engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": self.ctx.project_id},
            )
            conn.commit()

            result = conn.execute(
                text(
                    """
                    SELECT * FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                    ORDER BY version DESC
                    """
                ),
                {
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )
            rows = result.fetchall()

        history = [self._row_to_history(row) for row in rows]

        self._audit_mapping_event(
            event_type="mapping.query",
            unified_id=unified_id,
            entity_type=entity_type,
            details={
                "operation": "history",
                "version_count": len(history),
            },
        )

        return history

    def soft_delete_mapping(
        self,
        unified_id: str,
        entity_type: EntityType,
    ) -> bool:
        """Soft delete a mapping by marking current version as expired.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type

        Returns:
            True if deleted, False if not found

        Raises:
            AppError: If permission denied
        """
        self._require_write_permission()

        now = datetime.now(timezone.utc)

        with self._engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": self.ctx.project_id},
            )

            # Get current version to audit
            current_result = conn.execute(
                text(
                    """
                    SELECT version FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                      AND valid_to IS NULL
                    """
                ),
                {
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )
            current_row = current_result.fetchone()

            if current_row is None:
                self._audit_mapping_event(
                    event_type="mapping.delete",
                    unified_id=unified_id,
                    entity_type=entity_type,
                    details={"result": "not_found"},
                    result_status="failure",
                    error_code=ErrorCode.NOT_FOUND.value,
                )
                return False

            deleted_version = current_row.version

            # Mark as expired
            conn.execute(
                text(
                    """
                    UPDATE entity_mappings
                    SET valid_to = :now
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                      AND valid_to IS NULL
                    """
                ),
                {
                    "now": now,
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )

        self._audit_mapping_event(
            event_type="mapping.delete",
            unified_id=unified_id,
            entity_type=entity_type,
            version=deleted_version,
            details={"result": "soft_deleted"},
        )

        logger.info(
            "mapping_deleted",
            unified_id=unified_id,
            entity_type=entity_type.value,
            version=deleted_version,
            tenant_id=self.ctx.tenant_id,
            project_id=self.ctx.project_id,
            request_id=self.ctx.request_id,
        )

        return True

    def check_version_conflict(
        self,
        unified_id: str,
        entity_type: EntityType,
        expected_version: int,
    ) -> Tuple[bool, Optional[int]]:
        """Check for version conflict (optimistic locking).

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type
            expected_version: Expected current version

        Returns:
            Tuple of (has_conflict, actual_current_version)
            - has_conflict: True if expected_version != actual version
            - actual_current_version: Current version in database (None if not found)
        """
        self._require_read_permission()

        with self._engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": self.ctx.project_id},
            )
            conn.commit()

            result = conn.execute(
                text(
                    """
                    SELECT version FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                      AND valid_to IS NULL
                    """
                ),
                {
                    "tenant_id": self.ctx.tenant_id,
                    "project_id": self.ctx.project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )
            row = result.fetchone()

        if row is None:
            return True, None

        actual_version = row.version
        has_conflict = actual_version != expected_version

        if has_conflict:
            self._audit_mapping_event(
                event_type="mapping.conflict_detected",
                unified_id=unified_id,
                entity_type=entity_type,
                details={
                    "expected_version": expected_version,
                    "actual_version": actual_version,
                    "conflict_type": "VERSION_MISMATCH",
                },
            )

        return has_conflict, actual_version

    def get_all_mappings_for_unified_id(
        self,
        unified_id: str,
        entity_type: EntityType,
        tenant_id: str,
        project_id: str,
    ) -> List[EntityMappingResponse]:
        """Get all mappings for a unified_id across all source systems.

        This method is used by ConflictDetector to detect multi-to-one conflicts.

        Args:
            unified_id: Unified entity ID
            entity_type: Entity type
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation

        Returns:
            List of all mappings for this unified_id (empty if none)
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT * FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND unified_id = :unified_id
                      AND entity_type = :entity_type
                      AND valid_to IS NULL
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "unified_id": unified_id,
                    "entity_type": entity_type.value,
                },
            )
            rows = result.fetchall()

        return [self._row_to_response(row) for row in rows]

    def get_mappings_by_source_id(
        self,
        source_system: str,
        source_id: str,
        tenant_id: str,
        project_id: str,
    ) -> List[EntityMappingResponse]:
        """Get all mappings by source system ID (reverse lookup).

        This method is used by ConflictDetector to detect cross-system conflicts.

        Args:
            source_system: Source system name (ERP/MES/DCS/EAM)
            source_id: Source system original ID
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation

        Returns:
            List of mappings for this source_id (may be multiple if conflicts)
        """
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT * FROM entity_mappings
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND source_system = :source_system
                      AND source_id = :source_id
                      AND valid_to IS NULL
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_system": source_system,
                    "source_id": source_id,
                },
            )
            rows = result.fetchall()

        return [self._row_to_response(row) for row in rows]

    def get_unified_ids_with_multiple_mappings(
        self,
        tenant_id: str,
        project_id: str,
        entity_type: Optional[EntityType] = None,
    ) -> Dict[str, List[EntityMappingResponse]]:
        """Get all unified_ids that have multiple mappings (potential conflicts).

        This method is used by ConflictDetector for multi-to-one conflict scanning.

        Args:
            tenant_id: Tenant ID for isolation
            project_id: Project ID for isolation
            entity_type: Optional filter by entity type

        Returns:
            Dictionary mapping unified_id to list of its mappings
        """
        with self._engine.connect() as conn:
            if entity_type:
                result = conn.execute(
                    text(
                        """
                        SELECT * FROM entity_mappings
                        WHERE tenant_id = :tenant_id
                          AND project_id = :project_id
                          AND entity_type = :entity_type
                          AND valid_to IS NULL
                          AND unified_id IN (
                              SELECT unified_id
                              FROM entity_mappings
                              WHERE tenant_id = :tenant_id
                                AND project_id = :project_id
                                AND entity_type = :entity_type
                                AND valid_to IS NULL
                              GROUP BY unified_id
                              HAVING COUNT(*) > 1
                          )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "entity_type": entity_type.value,
                    },
                )
            else:
                result = conn.execute(
                    text(
                        """
                        SELECT * FROM entity_mappings
                        WHERE tenant_id = :tenant_id
                          AND project_id = :project_id
                          AND valid_to IS NULL
                          AND unified_id IN (
                              SELECT unified_id
                              FROM entity_mappings
                              WHERE tenant_id = :tenant_id
                                AND project_id = :project_id
                                AND valid_to IS NULL
                              GROUP BY unified_id
                              HAVING COUNT(*) > 1
                          )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                    },
                )
            rows = result.fetchall()

        # Group by unified_id
        grouped: Dict[str, List[EntityMappingResponse]] = {}
        for row in rows:
            mapping = self._row_to_response(row)
            if mapping.unified_id not in grouped:
                grouped[mapping.unified_id] = []
            grouped[mapping.unified_id].append(mapping)

        return grouped
