"""Semantic layer models package."""

from gangqing.semantic.mapping_evidence import (
    MappingEvidence,
    MappingEvidenceBuilder,
    create_mapping_evidence_builder,
)
from gangqing.semantic.models.conflict_detection import (
    ConflictAuditEvent,
    ConflictDetectionResult,
    ConflictResolutionStrategy,
    ConflictType,
    DegradedResult,
)
from gangqing.semantic.models.entity_mapping import (
    EntityMappingBase,
    EntityMappingCreate,
    EntityMappingResponse,
    EntityMappingUpdate,
    EntityType,
    MappingAuditEvent,
    MappingConflictError,
    MappingVersionHistory,
    MAPPING_CONFLICT_READ_CAPABILITY,
    MAPPING_READ_CAPABILITY,
    MAPPING_WRITE_CAPABILITY,
)

__all__ = [
    # Entity mapping models
    "EntityType",
    "EntityMappingBase",
    "EntityMappingCreate",
    "EntityMappingUpdate",
    "EntityMappingResponse",
    "MappingVersionHistory",
    "MappingConflictError",
    "MappingAuditEvent",
    "MAPPING_READ_CAPABILITY",
    "MAPPING_WRITE_CAPABILITY",
    "MAPPING_CONFLICT_READ_CAPABILITY",
    # Conflict detection models
    "ConflictType",
    "ConflictDetectionResult",
    "ConflictResolutionStrategy",
    "DegradedResult",
    "ConflictAuditEvent",
    # Mapping evidence models
    "MappingEvidence",
    "MappingEvidenceBuilder",
    "create_mapping_evidence_builder",
]
