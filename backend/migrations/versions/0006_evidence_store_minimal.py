"""evidence store minimal

Revision ID: 0006_evidence_store
Revises: 0005_draft_min_persist
Create Date: 2026-03-12

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_evidence_store"
down_revision = "0005_draft_min_persist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_store",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_store"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "request_id",
            "evidence_id",
            name="uq_evidence_store_scope_request_evidence",
        ),
    )
    op.create_index(
        "idx_evidence_store_scope_request",
        "evidence_store",
        ["tenant_id", "project_id", "request_id"],
        unique=False,
    )

    op.execute(
        """
        ALTER TABLE evidence_store ENABLE ROW LEVEL SECURITY;
        ALTER TABLE evidence_store FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS p_evidence_store_isolation ON evidence_store;
        CREATE POLICY p_evidence_store_isolation ON evidence_store
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

    op.execute(
        """
        REVOKE ALL ON TABLE evidence_store FROM PUBLIC;
        GRANT SELECT, INSERT, UPDATE ON TABLE evidence_store TO gangqing_app;
        GRANT SELECT ON TABLE evidence_store TO gangqing_auditor;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS p_evidence_store_isolation ON evidence_store;
        ALTER TABLE IF EXISTS evidence_store NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE IF EXISTS evidence_store DISABLE ROW LEVEL SECURITY;
        """
    )
    op.drop_index("idx_evidence_store_scope_request", table_name="evidence_store")
    op.drop_table("evidence_store")
