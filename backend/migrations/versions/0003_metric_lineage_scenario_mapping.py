"""metric lineage scenario mapping

Revision ID: 0003_ml_scn_map
Revises: 0002_metric_lineage
Create Date: 2026-02-20

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_ml_scn_map"
down_revision = "0002_metric_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_lineage_scenario_mapping",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("scenario_key", sa.Text(), nullable=False),
        sa.Column("lineage_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_metric_lineage_scenario_mapping"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "metric_name",
            "scenario_key",
            "lineage_version",
            name="uq_ml_scn_map_scope_metric_scn_ver",
        ),
    )

    op.create_index(
        "idx_metric_lineage_scenario_mapping_scope_metric_scenario",
        "metric_lineage_scenario_mapping",
        ["tenant_id", "project_id", "metric_name", "scenario_key"],
        unique=False,
    )

    op.create_index(
        "uq_ml_scn_map_scope_metric_scn_active_u",
        "metric_lineage_scenario_mapping",
        ["tenant_id", "project_id", "metric_name", "scenario_key"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.execute(
        """
        ALTER TABLE metric_lineage_scenario_mapping ENABLE ROW LEVEL SECURITY;
        ALTER TABLE metric_lineage_scenario_mapping FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_metric_lineage_scenario_mapping_isolation ON metric_lineage_scenario_mapping;
        CREATE POLICY p_metric_lineage_scenario_mapping_isolation ON metric_lineage_scenario_mapping
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS p_metric_lineage_scenario_mapping_isolation ON metric_lineage_scenario_mapping;
        ALTER TABLE IF EXISTS metric_lineage_scenario_mapping NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS metric_lineage_scenario_mapping DISABLE ROW LEVEL SECURITY;
        """
    )

    op.drop_index(
        "uq_ml_scn_map_scope_metric_scn_active_u",
        table_name="metric_lineage_scenario_mapping",
    )
    op.drop_index(
        "idx_metric_lineage_scenario_mapping_scope_metric_scenario",
        table_name="metric_lineage_scenario_mapping",
    )
    op.drop_table("metric_lineage_scenario_mapping")
