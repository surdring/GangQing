"""init min schema

Revision ID: 0001_init_min_schema
Revises: 
Create Date: 2026-02-19

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_init_min_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # dim_equipment: equipment dimension.
    # - Isolation: tenant_id + project_id
    # - Uniqueness: (tenant_id, project_id, unified_equipment_id)
    # - Query path: scope + unified_equipment_id
    op.create_table(
        "dim_equipment",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("unified_equipment_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=True),
        sa.Column("area", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dim_equipment"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "unified_equipment_id",
            name="uq_dim_equipment_scope_unified_equipment_id",
        ),
    )
    op.create_index(
        "idx_dim_equipment_scope_unified_id",
        "dim_equipment",
        ["tenant_id", "project_id", "unified_equipment_id"],
        unique=False,
    )

    # dim_material: material dimension.
    # - Isolation: tenant_id + project_id
    # - Uniqueness: (tenant_id, project_id, unified_material_id)
    # - Query path: scope + unified_material_id
    op.create_table(
        "dim_material",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("unified_material_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dim_material"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "unified_material_id",
            name="uq_dim_material_scope_unified_material_id",
        ),
    )
    op.create_index(
        "idx_dim_material_scope_unified_id",
        "dim_material",
        ["tenant_id", "project_id", "unified_material_id"],
        unique=False,
    )

    # metric_lineage: metric definition/lineage repository.
    # - Isolation: tenant_id + project_id
    # - Uniqueness: (tenant_id, project_id, metric_name, lineage_version)
    op.create_table(
        "metric_lineage",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("lineage_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("source_systems", sa.JSON(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_metric_lineage"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "metric_name",
            "lineage_version",
            name="uq_metric_lineage_scope_metric_version",
        ),
    )

    # fact_production_daily: daily production facts.
    # - Isolation: tenant_id + project_id
    # - Time axis: business_date (+ optional time_start/time_end)
    # - Query path: scope + business_date + equipment_id
    op.create_table(
        "fact_production_daily",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("time_start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("time_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fact_production_daily"),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["dim_equipment.id"],
            name="fk_fact_production_daily_equipment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "business_date",
            "equipment_id",
            name="uq_fact_production_daily_scope_date_equipment",
        ),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_fact_production_daily_quantity_nonneg",
        ),
        sa.CheckConstraint(
            "time_end IS NULL OR time_start IS NULL OR time_end > time_start",
            name="ck_fact_production_daily_time_range",
        ),
    )
    op.create_index(
        "idx_fact_production_daily_scope_date_equipment",
        "fact_production_daily",
        ["tenant_id", "project_id", "business_date", "equipment_id"],
        unique=False,
    )

    # fact_energy_daily: daily energy consumption facts.
    # - Isolation: tenant_id + project_id
    # - Time axis: business_date
    # - Query path: scope + business_date + equipment_id + energy_type
    op.create_table(
        "fact_energy_daily",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("energy_type", sa.Text(), nullable=False),
        sa.Column("consumption", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("time_start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("time_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fact_energy_daily"),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["dim_equipment.id"],
            name="fk_fact_energy_daily_equipment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "business_date",
            "equipment_id",
            "energy_type",
            name="uq_fact_energy_daily_scope_date_equipment_type",
        ),
        sa.CheckConstraint(
            "consumption >= 0",
            name="ck_fact_energy_daily_consumption_nonneg",
        ),
        sa.CheckConstraint(
            "time_end IS NULL OR time_start IS NULL OR time_end > time_start",
            name="ck_fact_energy_daily_time_range",
        ),
    )
    op.create_index(
        "idx_fact_energy_daily_scope_date_equipment_type",
        "fact_energy_daily",
        ["tenant_id", "project_id", "business_date", "equipment_id", "energy_type"],
        unique=False,
    )

    # fact_cost_daily: daily cost facts bound to lineage_version.
    # - Isolation: tenant_id + project_id
    # - Time axis: business_date
    # - Query paths: (scope + date + equipment + lineage) and (scope + date + cost_item)
    op.create_table(
        "fact_cost_daily",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("cost_item", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("lineage_version", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("time_start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("time_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fact_cost_daily"),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["dim_equipment.id"],
            name="fk_fact_cost_daily_equipment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "business_date",
            "equipment_id",
            "cost_item",
            "lineage_version",
            name="uq_fact_cost_daily_scope_date_equipment_item_lineage",
        ),
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_fact_cost_daily_amount_nonneg",
        ),
        sa.CheckConstraint(
            "time_end IS NULL OR time_start IS NULL OR time_end > time_start",
            name="ck_fact_cost_daily_time_range",
        ),
    )
    op.create_index(
        "idx_fact_cost_daily_scope_date_equipment_lineage",
        "fact_cost_daily",
        ["tenant_id", "project_id", "business_date", "equipment_id", "lineage_version"],
        unique=False,
    )
    op.create_index(
        "idx_fact_cost_daily_scope_date_cost_item",
        "fact_cost_daily",
        ["tenant_id", "project_id", "business_date", "cost_item"],
        unique=False,
    )

    # fact_alarm_event: event facts (high volume) with RANGE partitioning by event_time.
    # - Isolation: tenant_id + project_id
    # - Time axis: event_time
    # - Query paths: scope + event_time, scope + equipment_id + event_time
    op.create_table(
        "fact_alarm_event",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("alarm_code", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", "event_time", name="pk_fact_alarm_event"),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["dim_equipment.id"],
            name="fk_fact_alarm_event_equipment_id",
            ondelete="RESTRICT",
        ),
        postgresql_partition_by="RANGE (event_time)",
    )

    op.execute(
        """
        CREATE TABLE fact_alarm_event_p0
        PARTITION OF fact_alarm_event
        FOR VALUES FROM ('2000-01-01') TO ('2100-01-01');
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX idx_fact_alarm_event_p0_id_unique
        ON fact_alarm_event_p0 (id);
        """
    )
    op.create_index(
        "idx_fact_alarm_event_scope_time",
        "fact_alarm_event",
        ["tenant_id", "project_id", "event_time"],
        unique=False,
    )
    op.create_index(
        "idx_fact_alarm_event_scope_equipment_time",
        "fact_alarm_event",
        ["tenant_id", "project_id", "equipment_id", "event_time"],
        unique=False,
    )

    # fact_maintenance_workorder: maintenance work orders.
    # - Isolation: tenant_id + project_id
    # - Time axis: created_time
    # - Query paths: scope + workorder_no, scope + equipment_id + created_time
    op.create_table(
        "fact_maintenance_workorder",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("workorder_no", sa.Text(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("closed_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("fault_code", sa.Text(), nullable=True),
        sa.Column("fault_desc", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fact_maintenance_workorder"),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["dim_equipment.id"],
            name="fk_fact_maintenance_workorder_equipment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "workorder_no",
            name="uq_fact_maintenance_workorder_scope_workorder_no",
        ),
        sa.CheckConstraint(
            "closed_time IS NULL OR closed_time >= created_time",
            name="ck_fact_maintenance_workorder_closed_after_created",
        ),
    )
    op.create_index(
        "idx_fact_maintenance_workorder_scope_workorder_no",
        "fact_maintenance_workorder",
        ["tenant_id", "project_id", "workorder_no"],
        unique=False,
    )
    op.create_index(
        "idx_fact_maintenance_workorder_scope_equipment_created",
        "fact_maintenance_workorder",
        ["tenant_id", "project_id", "equipment_id", "created_time"],
        unique=False,
    )

    # audit_log: append-only audit events with RANGE partitioning by timestamp.
    # - Isolation: tenant_id + project_id
    # - Append-only: UPDATE/DELETE blocked (trigger) + permissions model (DB roles)
    # - Query paths: scope + request_id + timestamp, scope + timestamp
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("action_summary", sa.JSON(), nullable=True),
        sa.Column("result_status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", "timestamp", name="pk_audit_log"),
        postgresql_partition_by="RANGE (timestamp)",
    )

    op.execute(
        """
        CREATE TABLE audit_log_p0
        PARTITION OF audit_log
        FOR VALUES FROM ('2000-01-01') TO ('2100-01-01');
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX idx_audit_log_p0_id_unique
        ON audit_log_p0 (id);
        """
    )
    op.create_index(
        "idx_audit_log_scope_request_time",
        "audit_log",
        ["tenant_id", "project_id", "request_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_audit_log_scope_time",
        "audit_log",
        ["tenant_id", "project_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_audit_log_scope_event_type_time",
        "audit_log",
        ["tenant_id", "project_id", "event_type", "timestamp"],
        unique=False,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_block_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_no_update
        BEFORE UPDATE ON audit_log_p0
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_no_delete
        BEFORE DELETE ON audit_log_p0
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation();
        """
    )

    # audit_log permissions & ownership model:
    # - gangqing_migrator owns audit tables (DDL authority)
    # - gangqing_app can SELECT/INSERT only (no UPDATE/DELETE)
    # - gangqing_auditor can SELECT only
    # Note: superuser/BYPASSRLS roles can bypass RLS; application role must not have those privileges.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gangqing_migrator') THEN
                CREATE ROLE gangqing_migrator;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gangqing_app') THEN
                CREATE ROLE gangqing_app;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gangqing_auditor') THEN
                CREATE ROLE gangqing_auditor;
            END IF;
        END
        $$;

        REVOKE ALL ON TABLE audit_log FROM PUBLIC;
        REVOKE ALL ON TABLE audit_log_p0 FROM PUBLIC;

        ALTER TABLE audit_log OWNER TO gangqing_migrator;
        ALTER TABLE audit_log_p0 OWNER TO gangqing_migrator;

        GRANT USAGE ON SCHEMA public TO gangqing_app;
        GRANT USAGE ON SCHEMA public TO gangqing_auditor;

        GRANT SELECT, INSERT ON TABLE audit_log TO gangqing_app;
        GRANT SELECT, INSERT ON TABLE audit_log_p0 TO gangqing_app;

        GRANT SELECT ON TABLE audit_log TO gangqing_auditor;
        GRANT SELECT ON TABLE audit_log_p0 TO gangqing_auditor;
        """
    )

    # RLS (Row Level Security) as a DB-side isolation backstop.
    # Policies rely on session GUC variables:
    # - app.current_tenant
    # - app.current_project
    # FORCE ROW LEVEL SECURITY prevents table owners from bypassing policies.
    op.execute(
        """
        ALTER TABLE dim_equipment ENABLE ROW LEVEL SECURITY;
        ALTER TABLE dim_equipment FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_dim_equipment_isolation ON dim_equipment;
        CREATE POLICY p_dim_equipment_isolation ON dim_equipment
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE dim_material ENABLE ROW LEVEL SECURITY;
        ALTER TABLE dim_material FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_dim_material_isolation ON dim_material;
        CREATE POLICY p_dim_material_isolation ON dim_material
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE metric_lineage ENABLE ROW LEVEL SECURITY;
        ALTER TABLE metric_lineage FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_metric_lineage_isolation ON metric_lineage;
        CREATE POLICY p_metric_lineage_isolation ON metric_lineage
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE fact_production_daily ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fact_production_daily FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_fact_production_daily_isolation ON fact_production_daily;
        CREATE POLICY p_fact_production_daily_isolation ON fact_production_daily
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE fact_energy_daily ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fact_energy_daily FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_fact_energy_daily_isolation ON fact_energy_daily;
        CREATE POLICY p_fact_energy_daily_isolation ON fact_energy_daily
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE fact_cost_daily ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fact_cost_daily FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_fact_cost_daily_isolation ON fact_cost_daily;
        CREATE POLICY p_fact_cost_daily_isolation ON fact_cost_daily
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE fact_alarm_event ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fact_alarm_event FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_fact_alarm_event_isolation ON fact_alarm_event;
        CREATE POLICY p_fact_alarm_event_isolation ON fact_alarm_event
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE fact_alarm_event_p0 ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fact_alarm_event_p0 FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_fact_alarm_event_p0_isolation ON fact_alarm_event_p0;
        CREATE POLICY p_fact_alarm_event_p0_isolation ON fact_alarm_event_p0
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE fact_maintenance_workorder ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fact_maintenance_workorder FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_fact_maintenance_workorder_isolation ON fact_maintenance_workorder;
        CREATE POLICY p_fact_maintenance_workorder_isolation ON fact_maintenance_workorder
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
        ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_audit_log_isolation ON audit_log;
        CREATE POLICY p_audit_log_isolation ON audit_log
            USING (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            )
            WITH CHECK (
                tenant_id = current_setting('app.current_tenant', true)
                AND project_id = current_setting('app.current_project', true)
            );

        ALTER TABLE audit_log_p0 ENABLE ROW LEVEL SECURITY;
        ALTER TABLE audit_log_p0 FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_audit_log_p0_isolation ON audit_log_p0;
        CREATE POLICY p_audit_log_p0_isolation ON audit_log_p0
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
        DROP POLICY IF EXISTS p_audit_log_p0_isolation ON audit_log_p0;
        DROP POLICY IF EXISTS p_audit_log_isolation ON audit_log;
        DROP POLICY IF EXISTS p_fact_maintenance_workorder_isolation ON fact_maintenance_workorder;
        DROP POLICY IF EXISTS p_fact_alarm_event_p0_isolation ON fact_alarm_event_p0;
        DROP POLICY IF EXISTS p_fact_alarm_event_isolation ON fact_alarm_event;
        DROP POLICY IF EXISTS p_fact_cost_daily_isolation ON fact_cost_daily;
        DROP POLICY IF EXISTS p_fact_energy_daily_isolation ON fact_energy_daily;
        DROP POLICY IF EXISTS p_fact_production_daily_isolation ON fact_production_daily;
        DROP POLICY IF EXISTS p_metric_lineage_isolation ON metric_lineage;
        DROP POLICY IF EXISTS p_dim_material_isolation ON dim_material;
        DROP POLICY IF EXISTS p_dim_equipment_isolation ON dim_equipment;

        ALTER TABLE IF EXISTS audit_log_p0 NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS audit_log NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_alarm_event_p0 NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_alarm_event NO FORCE ROW LEVEL SECURITY;

        ALTER TABLE IF EXISTS audit_log_p0 DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS audit_log DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_maintenance_workorder DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_alarm_event_p0 DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_alarm_event DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_cost_daily DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_energy_daily DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS fact_production_daily DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS metric_lineage DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS dim_material DISABLE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS dim_equipment DISABLE ROW LEVEL SECURITY;
        """
    )

    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log_p0")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log_p0")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation")

    op.execute("DROP INDEX IF EXISTS idx_audit_log_p0_id_unique")

    op.drop_index("idx_audit_log_scope_event_type_time", table_name="audit_log")
    op.drop_index("idx_audit_log_scope_time", table_name="audit_log")
    op.drop_index("idx_audit_log_scope_request_time", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("idx_fact_maintenance_workorder_scope_equipment_created", table_name="fact_maintenance_workorder")
    op.drop_index("idx_fact_maintenance_workorder_scope_workorder_no", table_name="fact_maintenance_workorder")
    op.drop_table("fact_maintenance_workorder")

    op.execute("DROP INDEX IF EXISTS idx_fact_alarm_event_p0_id_unique")
    op.drop_index("idx_fact_alarm_event_scope_equipment_time", table_name="fact_alarm_event")
    op.drop_index("idx_fact_alarm_event_scope_time", table_name="fact_alarm_event")
    op.drop_table("fact_alarm_event")

    op.drop_index("idx_fact_cost_daily_scope_date_cost_item", table_name="fact_cost_daily")
    op.drop_index("idx_fact_cost_daily_scope_date_equipment_lineage", table_name="fact_cost_daily")
    op.drop_table("fact_cost_daily")

    op.drop_index("idx_fact_energy_daily_scope_date_equipment_type", table_name="fact_energy_daily")
    op.drop_table("fact_energy_daily")

    op.drop_index("idx_fact_production_daily_scope_date_equipment", table_name="fact_production_daily")
    op.drop_table("fact_production_daily")

    op.drop_table("metric_lineage")

    op.drop_index("idx_dim_material_scope_unified_id", table_name="dim_material")
    op.drop_table("dim_material")

    op.drop_index("idx_dim_equipment_scope_unified_id", table_name="dim_equipment")
    op.drop_table("dim_equipment")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gangqing_auditor') THEN
                REVOKE ALL PRIVILEGES ON SCHEMA public FROM gangqing_auditor;
                DROP OWNED BY gangqing_auditor;
                DROP ROLE gangqing_auditor;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gangqing_app') THEN
                REVOKE ALL PRIVILEGES ON SCHEMA public FROM gangqing_app;
                DROP OWNED BY gangqing_app;
                DROP ROLE gangqing_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gangqing_migrator') THEN
                REVOKE ALL PRIVILEGES ON SCHEMA public FROM gangqing_migrator;
                DROP OWNED BY gangqing_migrator;
                DROP ROLE gangqing_migrator;
            END IF;
        END
        $$;
        """
    )
