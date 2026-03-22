"""fact enums check constraints

Revision ID: 0004_fact_enums
Revises: 0003_ml_scn_map
Create Date: 2026-02-27

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_fact_enums"
down_revision = "0003_ml_scn_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_fact_alarm_event_severity_enum",
        "fact_alarm_event",
        sa.text(
            "severity IS NULL OR severity IN ('low', 'medium', 'high', 'critical')"
        ),
    )

    op.create_check_constraint(
        "ck_fact_maintenance_workorder_status_enum",
        "fact_maintenance_workorder",
        sa.text("status IN ('open', 'in_progress', 'closed', 'cancelled')"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_fact_maintenance_workorder_status_enum",
        "fact_maintenance_workorder",
        type_="check",
    )
    op.drop_constraint(
        "ck_fact_alarm_event_severity_enum",
        "fact_alarm_event",
        type_="check",
    )
