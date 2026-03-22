"""draft minimal persistence

Revision ID: 0005_draft_min_persist
Revises: 0004_fact_enums
Create Date: 2026-03-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_draft_min_persist"
down_revision = "0004_fact_enums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("draft_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_draft"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "draft_id",
            name="uq_draft_scope_draft_id",
        ),
    )
    op.create_index(
        "idx_draft_scope_draft_id",
        "draft",
        ["tenant_id", "project_id", "draft_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_draft_scope_draft_id", table_name="draft")
    op.drop_table("draft")
