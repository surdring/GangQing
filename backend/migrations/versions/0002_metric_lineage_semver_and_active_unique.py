"""metric lineage semver and active uniqueness

Revision ID: 0002_metric_lineage
Revises: 0001_init_min_schema
Create Date: 2026-02-20

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_metric_lineage"
down_revision = "0001_init_min_schema"
branch_labels = None
depends_on = None


_SEMVER_REGEX = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"


def upgrade() -> None:
    op.create_check_constraint(
        "ck_metric_lineage_lineage_version_semver",
        "metric_lineage",
        sa.text(f"lineage_version ~ '{_SEMVER_REGEX}'"),
    )

    op.create_index(
        "uq_metric_lineage_scope_metric_active_unique",
        "metric_lineage",
        ["tenant_id", "project_id", "metric_name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_metric_lineage_scope_metric_active_unique",
        table_name="metric_lineage",
    )
    op.drop_constraint(
        "ck_metric_lineage_lineage_version_semver",
        "metric_lineage",
        type_="check",
    )
    
