"""Semantic layer models for entity mapping and unified ID management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator


class EntityType(str, Enum):
    """Entity types supported in the unified ID mapping system."""

    EQUIPMENT = "equipment"
    MATERIAL = "material"
    BATCH = "batch"
    ORDER = "order"


class MappingVersionHistory(BaseModel):
    """Model for mapping version history entry."""

    unified_id: str = Field(min_length=1, description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    version: int = Field(ge=1, description="Version number")
    source_system: str = Field(min_length=1, description="Source system name")
    source_id: str = Field(min_length=1, description="Source system original ID")
    valid_from: datetime = Field(description="Version effective time")
    valid_to: Optional[datetime] = Field(default=None, description="Version expiration time")
    created_by: Optional[str] = Field(default=None, description="Creator user ID")
    tenant_id: str = Field(min_length=1, description="Tenant ID for isolation")
    project_id: str = Field(min_length=1, description="Project ID for isolation")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extended metadata")

    model_config = {"populate_by_name": True}


class EntityMappingBase(BaseModel):
    """Base Pydantic model for entity mapping."""

    unified_id: str = Field(min_length=1, description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    source_system: str = Field(min_length=1, description="Source system (ERP/MES/DCS/EAM)")
    source_id: str = Field(min_length=1, description="Source system original ID")
    tenant_id: str = Field(min_length=1, description="Tenant ID (mandatory isolation)")
    project_id: str = Field(min_length=1, description="Project ID (mandatory isolation)")
    version: int = Field(ge=1, default=1, description="Version number, starts from 1")
    valid_from: datetime = Field(default_factory=datetime.utcnow, description="Version effective time")
    valid_to: Optional[datetime] = Field(default=None, description="Version expiration time (null for current version)")
    created_by: Optional[str] = Field(default=None, description="Creator user ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extended metadata")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_version_logic(self) -> "EntityMappingBase":
        """Validate version logic: valid_to must be after valid_for current versions."""
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class EntityMappingCreate(BaseModel):
    """Model for creating a new entity mapping."""

    unified_id: str = Field(min_length=1, description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    source_system: str = Field(min_length=1, description="Source system (ERP/MES/DCS/EAM)")
    source_id: str = Field(min_length=1, description="Source system original ID")
    tenant_id: str = Field(min_length=1, description="Tenant ID (mandatory isolation)")
    project_id: str = Field(min_length=1, description="Project ID (mandatory isolation)")
    created_by: Optional[str] = Field(default=None, description="Creator user ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extended metadata")

    model_config = {"populate_by_name": True}


class EntityMappingUpdate(BaseModel):
    """Model for updating an existing entity mapping.

    Updates create a new version while marking the old version as expired.
    """

    source_system: Optional[str] = Field(default=None, min_length=1, description="Source system (ERP/MES/DCS/EAM)")
    source_id: Optional[str] = Field(default=None, min_length=1, description="Source system original ID")
    updated_by: Optional[str] = Field(default=None, description="Updater user ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extended metadata (merged with existing)")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "EntityMappingUpdate":
        """Validate that at least one field is being updated."""
        if (
            self.source_system is None
            and self.source_id is None
            and self.metadata is None
        ):
            raise ValueError("At least one field must be provided for update")
        return self


class EntityMappingResponse(BaseModel):
    """Response model for entity mapping operations."""

    unified_id: str = Field(description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    source_system: str = Field(description="Source system")
    source_id: str = Field(description="Source system original ID")
    tenant_id: str = Field(description="Tenant ID")
    project_id: str = Field(description="Project ID")
    version: int = Field(description="Version number")
    valid_from: datetime = Field(description="Version effective time")
    valid_to: Optional[datetime] = Field(default=None, description="Version expiration time")
    created_by: Optional[str] = Field(default=None, description="Creator user ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extended metadata")

    model_config = {"populate_by_name": True}


class MappingConflictError(BaseModel):
    """Model for mapping conflict detection result."""

    unified_id: str = Field(description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    expected_version: int = Field(description="Expected version")
    actual_version: int = Field(description="Actual current version")
    conflict_type: str = Field(default="VERSION_MISMATCH", description="Conflict type")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp")

    model_config = {"populate_by_name": True}


class MappingAuditEvent(BaseModel):
    """Audit event model for mapping operations."""

    event_type: str = Field(description="Event type (mapping.create/mapping.update/mapping.delete/mapping.query)")
    unified_id: str = Field(description="Unified entity ID")
    entity_type: EntityType = Field(description="Entity type")
    version: Optional[int] = Field(default=None, description="Version number")
    tenant_id: str = Field(description="Tenant ID")
    project_id: str = Field(description="Project ID")
    user_id: Optional[str] = Field(default=None, description="User ID who performed the action")
    request_id: str = Field(description="Request ID for tracing")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional event details")

    model_config = {"populate_by_name": True}


# Capability constants for RBAC
MAPPING_READ_CAPABILITY = "semantic:mapping:read"
MAPPING_WRITE_CAPABILITY = "semantic:mapping:write"
MAPPING_CONFLICT_READ_CAPABILITY = "semantic:mapping:conflict:read"
