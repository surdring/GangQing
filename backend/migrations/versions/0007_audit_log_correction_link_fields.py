"""audit log correction link fields

Revision ID: 0007_audit_corr_link
Revises: 0006_evidence_store
Create Date: 2026-03-17

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_audit_corr_link"
down_revision = "0006_evidence_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("correlation_id", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("supersedes_event_id", sa.UUID(), nullable=True))

    op.create_index(
        "idx_audit_log_scope_correlation_time",
        "audit_log",
        ["tenant_id", "project_id", "correlation_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_audit_log_scope_correlation_time", table_name="audit_log")
    op.drop_column("audit_log", "supersedes_event_id")
    op.drop_column("audit_log", "correlation_id")
