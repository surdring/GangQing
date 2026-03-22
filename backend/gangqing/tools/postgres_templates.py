from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal


FilterOpLiteral = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "between"]


@dataclass(frozen=True)
class PostgresQueryTemplate:
    template_id: str
    description: str
    table_or_view: str
    time_field: str
    base_select_sql: str
    allowed_filter_fields: set[str]
    allowed_order_by_fields: set[str]
    required_hidden_fields: set[str]
    exposed_fields: list[str]


_TEMPLATES: dict[str, PostgresQueryTemplate] = {
    "production_daily": PostgresQueryTemplate(
        template_id="production_daily",
        description="Daily production facts",
        table_or_view="fact_production_daily",
        time_field="time_start",
        base_select_sql=(
            "SELECT tenant_id, project_id, business_date, equipment_id::text AS equipment_id, "
            "quantity, unit, source_system, source_record_id, time_start, time_end, extracted_at "
            "FROM fact_production_daily"
        ),
        allowed_filter_fields={"business_date", "equipment_id"},
        allowed_order_by_fields={"business_date", "quantity"},
        required_hidden_fields={"tenant_id", "project_id"},
        exposed_fields=[
            "business_date",
            "equipment_id",
            "quantity",
            "unit",
            "source_system",
            "source_record_id",
            "time_start",
            "time_end",
            "extracted_at",
        ],
    ),
    "production_daily_slow": PostgresQueryTemplate(
        template_id="production_daily_slow",
        description="Daily production facts (slow query probe)",
        table_or_view="fact_production_daily",
        time_field="time_start",
        base_select_sql=(
            "SELECT tenant_id, project_id, pg_sleep(1) AS __sleep, "
            "business_date, equipment_id::text AS equipment_id, "
            "quantity, unit, source_system, source_record_id, time_start, time_end, extracted_at "
            "FROM fact_production_daily"
        ),
        allowed_filter_fields={"business_date", "equipment_id"},
        allowed_order_by_fields={"business_date", "quantity"},
        required_hidden_fields={"tenant_id", "project_id"},
        exposed_fields=[
            "business_date",
            "equipment_id",
            "quantity",
            "unit",
            "source_system",
            "source_record_id",
            "time_start",
            "time_end",
            "extracted_at",
        ],
    ),
    "energy_daily": PostgresQueryTemplate(
        template_id="energy_daily",
        description="Daily energy facts",
        table_or_view="fact_energy_daily",
        time_field="time_start",
        base_select_sql=(
            "SELECT tenant_id, project_id, business_date, equipment_id::text AS equipment_id, "
            "energy_type, consumption, unit, source_system, source_record_id, "
            "time_start, time_end, extracted_at "
            "FROM fact_energy_daily"
        ),
        allowed_filter_fields={"business_date", "equipment_id", "energy_type"},
        allowed_order_by_fields={"business_date", "consumption"},
        required_hidden_fields={"tenant_id", "project_id"},
        exposed_fields=[
            "business_date",
            "equipment_id",
            "energy_type",
            "consumption",
            "unit",
            "source_system",
            "source_record_id",
            "time_start",
            "time_end",
            "extracted_at",
        ],
    ),
}


@lru_cache(maxsize=128)
def get_postgres_template(template_id: str) -> PostgresQueryTemplate:
    key = (template_id or "").strip()
    if not key:
        raise ValueError("templateId must not be empty")
    if key not in _TEMPLATES:
        raise ValueError("Unknown templateId")
    return _TEMPLATES[key]


def summarize_filter_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "bool"}
    if isinstance(value, int):
        return {"type": "int"}
    if isinstance(value, float):
        return {"type": "float"}
    if isinstance(value, str):
        return {"type": "str", "len": len(value)}
    if isinstance(value, list):
        types = sorted({type(v).__name__ for v in value})
        return {"type": "list", "len": len(value), "itemTypes": types}
    if isinstance(value, dict) and {"start", "end"}.issubset(value.keys()):
        return {"type": "range"}
    return {"type": "unknown"}
