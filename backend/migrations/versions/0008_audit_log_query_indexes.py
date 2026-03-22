"""audit log query indexes

Revision ID: 0008_audit_idx
Revises: 0007_audit_corr_link
Create Date: 2026-03-17

"""

from __future__ import annotations

from alembic import op

revision = "0008_audit_idx"
down_revision = "0007_audit_corr_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_audit_log_scope_user_time",
        "audit_log",
        ["tenant_id", "project_id", "user_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_audit_log_scope_resource_time",
        "audit_log",
        ["tenant_id", "project_id", "resource", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_audit_log_scope_resource_time", table_name="audit_log")
    op.drop_index("idx_audit_log_scope_user_time", table_name="audit_log")
