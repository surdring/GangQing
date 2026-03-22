"""Add entity mapping tables

Revision ID: 0009_add_entity_mapping_tables
Revises: 0008_audit_log_query_indexes
Create Date: 2026-03-22

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_add_entity_mapping_tables"
down_revision = "0008_audit_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create entity_mappings table with version management support."""
    # entity_mappings: unified ID mapping table with version management
    # - Isolation: tenant_id + project_id (mandatory)
    # - Uniqueness: (tenant_id, project_id, unified_id, entity_type, version)
    # - Query paths:
    #   1. Scope + entity_type + unified_id (by entity lookup)
    #   2. source_system + source_id (reverse lookup)
    #   3. valid_from + valid_to with valid_to IS NULL (current version lookup)
    op.create_table(
        "entity_mappings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("unified_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_entity_mappings"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "unified_id",
            "entity_type",
            "version",
            name="uq_entity_mappings_scope_unified_version",
        ),
    )

    # Index for querying by scope + entity_type + unified_id (primary lookup path)
    op.create_index(
        "idx_entity_mappings_scope_entity_unified",
        "entity_mappings",
        ["tenant_id", "project_id", "entity_type", "unified_id"],
        unique=False,
    )

    # Index for reverse lookup by source_system + source_id
    op.create_index(
        "idx_entity_mappings_source",
        "entity_mappings",
        ["source_system", "source_id"],
        unique=False,
    )

    # Index for time range queries
    op.create_index(
        "idx_entity_mappings_validity",
        "entity_mappings",
        ["valid_from", "valid_to"],
        unique=False,
    )

    # Partial index for current valid versions (valid_to IS NULL)
    op.create_index(
        "idx_entity_mappings_current",
        "entity_mappings",
        ["tenant_id", "project_id", "entity_type", "unified_id"],
        unique=False,
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # Check constraint for entity_type values
    op.create_check_constraint(
        "ck_entity_mappings_entity_type",
        "entity_mappings",
        sa.text("entity_type IN ('equipment', 'material', 'batch', 'order')"),
    )

    # Check constraint: valid_to must be after valid_from
    op.create_check_constraint(
        "ck_entity_mappings_validity_range",
        "entity_mappings",
        sa.text("valid_to IS NULL OR valid_to > valid_from"),
    )

    # Check constraint: version must be >= 1
    op.create_check_constraint(
        "ck_entity_mappings_version_positive",
        "entity_mappings",
        sa.text("version >= 1"),
    )


def downgrade() -> None:
    """Drop entity_mappings table."""
    op.drop_index("idx_entity_mappings_current", table_name="entity_mappings")
    op.drop_index("idx_entity_mappings_validity", table_name="entity_mappings")
    op.drop_index("idx_entity_mappings_source", table_name="entity_mappings")
    op.drop_index("idx_entity_mappings_scope_entity_unified", table_name="entity_mappings")
    op.drop_table("entity_mappings")
