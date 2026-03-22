from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from gangqing.common.audit import write_tool_call_event
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.masking import apply_evidence_role_based_masking, load_masking_policy
from gangqing.common.rbac import has_capability
from gangqing.common.settings import load_settings
from gangqing.tools.base import BaseReadOnlyToolMixin
from gangqing.tools.metadata import (
    ToolAccessMode,
    ToolContractRefs,
    ToolExecutionPolicy,
    ToolGovernance,
    ToolMetadata,
    ToolRbacPolicy,
    ToolRedactionPolicyRef,
)
from gangqing.tools.isolation import (
    build_scope_filter_summary,
    build_scope_where_sql,
    require_rows_in_scope,
    resolve_scope,
)
from gangqing.tools.rbac import require_tool_capability
from gangqing.tools.registry import tool_metadata
from gangqing_db.evidence import Evidence, EvidenceTimeRange
from gangqing_db.errors import MigrationError
from gangqing_db.postgres_query import execute_readonly_query, safe_extract_database_name
from gangqing_db.settings import load_settings as load_db_settings

from gangqing.tools.postgres_templates import get_postgres_template, summarize_filter_value


FilterOpLiteral = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "between"]
OrderDirLiteral = Literal["asc", "desc"]


class FilterCondition(BaseModel):
    field: str = Field(min_length=1)
    op: FilterOpLiteral
    value: Any


class OrderBy(BaseModel):
    field: str = Field(min_length=1)
    direction: OrderDirLiteral = "asc"


class PostgresReadOnlyQueryParams(BaseModel):
    tenant_id: str | None = Field(default=None, alias="tenantId")
    project_id: str | None = Field(default=None, alias="projectId")

    tool_call_id: str | None = Field(default=None, alias="toolCallId")

    template_id: str = Field(min_length=1, alias="templateId")

    time_range: EvidenceTimeRange = Field(alias="timeRange")
    filters: list[FilterCondition] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list, alias="orderBy")

    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0, le=100000)

    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")

    model_config = {"populate_by_name": True}

    @field_validator("filters")
    @classmethod
    def validate_filters_no_scope_override(cls, v: list[FilterCondition]) -> list[FilterCondition]:
        for c in v:
            if c.field in {"tenant_id", "project_id", "tenantId", "projectId"}:
                raise ValueError("filters must not include scope fields")
        return v


def _force_output_contract_violation_enabled() -> bool:
    return (os.getenv("GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION") or "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }


def _force_evidence_validation() -> str | None:
    value = (os.getenv("GANGQING_FORCE_POSTGRES_EVIDENCE_VALIDATION") or "").strip()
    if not value:
        return None
    value_norm = value.lower()
    allowed = {"verifiable", "not_verifiable", "out_of_bounds", "mismatch"}
    return value_norm if value_norm in allowed else None


class ColumnDef(BaseModel):
    name: str
    type: str


class PostgresReadOnlyQueryResult(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    rows: list[dict[str, Any]]
    row_count: int = Field(alias="rowCount")
    truncated: bool
    columns: list[ColumnDef] | None = None
    query_fingerprint: str = Field(alias="queryFingerprint")
    evidence: Evidence

    model_config = {"populate_by_name": True}


_FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|create|alter|drop|truncate|grant|revoke|copy|call|do|begin|commit|rollback)\b",
    re.IGNORECASE,
)


def _strip_sql_comments_and_whitespace(sql: str) -> str:
    """Normalize SQL for safety checks (strip comments/whitespace)."""
    value = (sql or "").strip()
    value = re.sub(r"/\*.*?\*/", " ", value, flags=re.DOTALL)
    value = re.sub(r"--.*?$", " ", value, flags=re.MULTILINE)
    return value.strip()


def _assert_select_only_sql(*, sql: str, ctx: RequestContext) -> None:
    """Enforce SELECT-only contract on generated SQL."""
    normalized = _strip_sql_comments_and_whitespace(sql)

    if ";" in normalized:
        raise AppError(
            ErrorCode.CONTRACT_VIOLATION,
            "Multiple SQL statements are not allowed",
            request_id=ctx.request_id,
            details=None,
            retryable=False,
        )

    if not normalized.lower().startswith("select"):
        raise AppError(
            ErrorCode.CONTRACT_VIOLATION,
            "Only SELECT statements are allowed",
            request_id=ctx.request_id,
            details=None,
            retryable=False,
        )

    if _FORBIDDEN_SQL_RE.search(normalized):
        raise AppError(
            ErrorCode.CONTRACT_VIOLATION,
            "SQL contains forbidden keywords",
            request_id=ctx.request_id,
            details=None,
            retryable=False,
        )


def _build_query_fingerprint(*, payload: dict[str, Any]) -> str:
    """Build a stable SHA-256 fingerprint for audit/evidence without leaking raw SQL."""
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _build_filters_summary(filters: list[FilterCondition]) -> list[dict[str, Any]]:
    """Summarize filters into redaction-safe structures for evidence/audit."""
    items: list[dict[str, Any]] = []
    for f in filters:
        items.append(
            {
                "field": f.field,
                "op": f.op,
                "value": summarize_filter_value(f.value),
            }
        )
    return items


def _build_filters_where_sql_and_params(
    *,
    filters: list[FilterCondition],
    ctx: RequestContext,
) -> tuple[list[str], dict[str, Any]]:
    where_parts: list[str] = []
    sql_params: dict[str, Any] = {}

    for idx, f in enumerate(filters):
        param_base = f"f_{idx}"
        if f.op == "eq":
            where_parts.append(f"{f.field} = :{param_base}")
            sql_params[param_base] = f.value
        elif f.op == "ne":
            where_parts.append(f"{f.field} != :{param_base}")
            sql_params[param_base] = f.value
        elif f.op == "gt":
            where_parts.append(f"{f.field} > :{param_base}")
            sql_params[param_base] = f.value
        elif f.op == "gte":
            where_parts.append(f"{f.field} >= :{param_base}")
            sql_params[param_base] = f.value
        elif f.op == "lt":
            where_parts.append(f"{f.field} < :{param_base}")
            sql_params[param_base] = f.value
        elif f.op == "lte":
            where_parts.append(f"{f.field} <= :{param_base}")
            sql_params[param_base] = f.value
        elif f.op == "in":
            if not isinstance(f.value, list) or not f.value:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "Filter 'in' expects a non-empty list",
                    request_id=ctx.request_id,
                    details={"field": f.field},
                    retryable=False,
                )
            where_parts.append(f"{f.field} = ANY(:{param_base})")
            sql_params[param_base] = f.value
        elif f.op == "between":
            if not isinstance(f.value, dict) or "start" not in f.value or "end" not in f.value:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "Filter 'between' expects an object with start/end",
                    request_id=ctx.request_id,
                    details={"field": f.field},
                    retryable=False,
                )
            where_parts.append(f"{f.field} >= :{param_base}_start AND {f.field} < :{param_base}_end")
            sql_params[f"{param_base}_start"] = f.value["start"]
            sql_params[f"{param_base}_end"] = f.value["end"]
        else:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Unsupported filter operator",
                request_id=ctx.request_id,
                details={"op": f.op},
                retryable=False,
            )

    return where_parts, sql_params


_REQUIRED_CAPABILITY = "tool:postgres:read"


def _build_postgres_readonly_tool_metadata() -> ToolMetadata:
    settings = load_settings()
    return ToolMetadata(
        toolName="postgres_readonly_query",
        version="1",
        enabled=True,
        governance=ToolGovernance(accessMode=ToolAccessMode.READ_ONLY, requiresApproval=False),
        rbac=ToolRbacPolicy(requiredCapability=_REQUIRED_CAPABILITY),
        execution=ToolExecutionPolicy(
            timeoutSeconds=float(settings.postgres_tool_default_timeout_seconds),
            maxRetries=int(settings.tool_max_retries),
        ),
        redaction=ToolRedactionPolicyRef(policyId="default"),
        contracts=ToolContractRefs(
            paramsModel="gangqing.tools.postgres_readonly.PostgresReadOnlyQueryParams",
            resultModel="gangqing.tools.postgres_readonly.PostgresReadOnlyQueryResult",
            outputContractSource="tool.postgres_readonly.result",
        ),
        dataDomains=["postgres"],
        tags=["readonly"],
    )


@tool_metadata(_build_postgres_readonly_tool_metadata())
class PostgresReadOnlyQueryTool(BaseReadOnlyToolMixin):
    name = "postgres_readonly_query"
    ParamsModel = PostgresReadOnlyQueryParams
    ResultModel = PostgresReadOnlyQueryResult
    required_capability = _REQUIRED_CAPABILITY
    output_contract_source = "tool.postgres_readonly.result"

    def __init__(
        self,
        *,
        execute_fn=execute_readonly_query,
        audit_fn=write_tool_call_event,
    ) -> None:
        self._execute_fn = execute_fn
        self._audit_fn = audit_fn

    def run(self, *, ctx: RequestContext, params: PostgresReadOnlyQueryParams) -> Any:
        start_time = time.perf_counter()

        def _duration_ms() -> int:
            return int((time.perf_counter() - start_time) * 1000)

        def _build_error_details(*, timeout_ms: int | None = None) -> dict[str, Any]:
            details: dict[str, Any] = {
                "toolName": self.name,
                "durationMs": _duration_ms(),
            }
            if timeout_ms is not None:
                details["timeoutMs"] = int(timeout_ms)
            return details

        capability = getattr(self, "required_capability", None)
        if capability:
            require_tool_capability(ctx=ctx, capability=capability, tool_name=self.name)

        settings = load_settings()

        try:
            tenant_id, project_id, scope_mode = resolve_scope(
                ctx=ctx,
                tenant_id=params.tenant_id,
                project_id=params.project_id,
            )
        except AppError as e:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "reason": "scope_rejected",
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=getattr(ctx, "tenant_id", None),
                        project_id=getattr(ctx, "project_id", None),
                        mode="rejected",
                    ),
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=e.code.value,
            )
            raise

        tool_call_id = (params.tool_call_id or "").strip() or uuid.uuid4().hex

        try:
            template = get_postgres_template(params.template_id)
        except ValueError as e:
            err = AppError(
                ErrorCode.VALIDATION_ERROR,
                "Unknown templateId",
                request_id=ctx.request_id,
                details={"reason": "unknown_template"},
                retryable=False,
            )
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "reason": "template_rejected",
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "templateId": params.template_id,
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=err.code.value,
            )
            raise err

        try:
            for f in params.filters:
                if f.field not in template.allowed_filter_fields:
                    raise AppError(
                        ErrorCode.VALIDATION_ERROR,
                        "Filter field is not allowed",
                        request_id=ctx.request_id,
                        details={"field": f.field},
                        retryable=False,
                    )
        except AppError as e:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "reason": "filters_rejected",
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=e.code.value,
            )
            raise

        try:
            for o in params.order_by:
                if o.field not in template.allowed_order_by_fields:
                    raise AppError(
                        ErrorCode.VALIDATION_ERROR,
                        "orderBy field is not allowed",
                        request_id=ctx.request_id,
                        details={"field": o.field},
                        retryable=False,
                    )
        except AppError as e:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "reason": "order_by_rejected",
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=e.code.value,
            )
            raise

        where_parts: list[str] = []
        sql_params: dict[str, Any] = {}

        scope_where, scope_params = build_scope_where_sql(tenant_id=tenant_id, project_id=project_id)
        where_parts.append(scope_where)
        sql_params.update(scope_params)

        where_parts.append(f"{template.time_field} >= :time_start AND {template.time_field} < :time_end")
        sql_params["time_start"] = params.time_range.start
        sql_params["time_end"] = params.time_range.end

        filter_where_parts, filter_params = _build_filters_where_sql_and_params(
            filters=params.filters,
            ctx=ctx,
        )
        where_parts.extend(filter_where_parts)
        sql_params.update(filter_params)

        order_by_sql = ""
        if params.order_by:
            order_parts: list[str] = []
            for o in params.order_by:
                direction = "ASC" if o.direction == "asc" else "DESC"
                order_parts.append(f"{o.field} {direction}")
            order_by_sql = " ORDER BY " + ", ".join(order_parts)

        where_sql = " WHERE " + " AND ".join(where_parts)

        sql = (
            f"{template.base_select_sql}"
            f"{where_sql}"
            f"{order_by_sql}"
            " LIMIT :limit OFFSET :offset"
        )
        sql_params["limit"] = int(params.limit)
        sql_params["offset"] = int(params.offset)

        filters_summary = _build_filters_summary(params.filters)
        fingerprint_payload = {
            "templateId": template.template_id,
            "tableOrView": template.table_or_view,
            "timeRange": {
                "start": params.time_range.start.isoformat(),
                "end": params.time_range.end.isoformat(),
            },
            "filters": filters_summary,
            "limit": params.limit,
            "offset": params.offset,
            "scopeMode": scope_mode,
        }
        query_fingerprint = _build_query_fingerprint(payload=fingerprint_payload)

        try:
            _assert_select_only_sql(sql=sql, ctx=ctx)
        except AppError as e:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "reason": "select_only_rejected",
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "templateId": template.template_id,
                    "queryFingerprint": query_fingerprint,
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=e.code.value,
            )
            raise

        timeout_seconds = float(settings.postgres_tool_default_timeout_seconds)
        if params.timeout_seconds is not None:
            if params.timeout_seconds <= 0:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "timeoutSeconds must be greater than 0",
                    request_id=ctx.request_id,
                    details=None,
                    retryable=False,
                )
            timeout_seconds = float(params.timeout_seconds)

        timeout_seconds = min(
            timeout_seconds,
            float(settings.postgres_tool_max_timeout_seconds),
        )
        timeout_ms = int(timeout_seconds * 1000)

        try:
            rows = self._execute_fn(
                sql=sql,
                params=sql_params,
                ctx=ctx,
                statement_timeout_ms=timeout_ms,
            )
        except MigrationError as e:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "templateId": template.template_id,
                    "queryFingerprint": query_fingerprint,
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=e.code.value,
            )

            try:
                common_code = ErrorCode(e.code.value)
            except Exception:
                common_code = ErrorCode.INTERNAL_ERROR

            raise AppError(
                common_code,
                e.message,
                request_id=ctx.request_id,
                details=_build_error_details(timeout_ms=timeout_ms),
                retryable=bool(e.retryable),
            ) from e

        try:
            require_rows_in_scope(ctx=ctx, rows=rows)
        except AppError as e:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "reason": "cross_scope_data_hit",
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "templateId": template.template_id,
                    "queryFingerprint": query_fingerprint,
                    "durationMs": _duration_ms(),
                },
                result_status="failure",
                error_code=e.code.value,
            )
            raise

        exposed_rows: list[dict[str, Any]] = []
        for r in rows:
            exposed_rows.append({k: r.get(k) for k in template.exposed_fields})

        base_evidence_id = f"pg:{template.template_id}:{query_fingerprint}"
        if len(base_evidence_id) > 128:
            digest = hashlib.sha256(base_evidence_id.encode("utf-8")).hexdigest()
            base_evidence_id = f"pg:{digest}"
        evidence_id = base_evidence_id
        extracted_at = datetime.now(timezone.utc)

        db_settings = load_db_settings()
        database_name = safe_extract_database_name(db_settings.database_url) or "unknown"

        evidence = Evidence(
            evidence_id=evidence_id,
            source_system="Postgres",
            source_locator={
                "database": database_name,
                "tableOrView": template.table_or_view,
                "timeField": template.time_field,
                "filters": filters_summary,
                "queryFingerprint": query_fingerprint,
                "templateId": template.template_id,
                "extractedAt": extracted_at.isoformat(),
            },
            time_range=params.time_range,
            tool_call_id=tool_call_id,
            lineage_version=None,
            data_quality_score=None,
            confidence="High",
            validation="verifiable",
            redactions=None,
        )

        try:
            masking_policy = load_masking_policy()
        except Exception:
            masking_policy = None
        role_raw = (getattr(ctx, "role", None) or "").strip() or None
        can_unmask = has_capability(role_raw=(role_raw or ""), capability="data:unmask:read")
        evidence = apply_evidence_role_based_masking(
            evidence,
            role=role_raw,
            can_unmask=can_unmask,
            policy=masking_policy,
        )

        forced_validation = _force_evidence_validation()
        if forced_validation is not None:
            evidence.validation = forced_validation

        result_summary = {
            "toolName": self.name,
            "rowCount": len(exposed_rows),
            "truncated": len(exposed_rows) >= params.limit,
            "queryFingerprint": query_fingerprint,
        }

        try:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                tool_call_id=tool_call_id,
                duration_ms=_duration_ms(),
                args_summary={
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "templateId": template.template_id,
                    "timeRange": fingerprint_payload["timeRange"],
                    "filters": filters_summary,
                    "limit": params.limit,
                    "offset": params.offset,
                    "queryFingerprint": query_fingerprint,
                    "rowCount": len(exposed_rows),
                    "durationMs": _duration_ms(),
                    "resultSummary": result_summary,
                },
                result_status="success",
                error_code=None,
                evidence_refs=[evidence_id],
            )
        except TypeError:
            self._audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={
                    "scopeFilter": build_scope_filter_summary(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        mode=scope_mode,
                    ),
                    "templateId": template.template_id,
                    "timeRange": fingerprint_payload["timeRange"],
                    "filters": filters_summary,
                    "limit": params.limit,
                    "offset": params.offset,
                    "queryFingerprint": query_fingerprint,
                    "rowCount": len(exposed_rows),
                    "durationMs": _duration_ms(),
                    "resultSummary": result_summary,
                },
                result_status="success",
                error_code=None,
                evidence_refs=[evidence_id],
            )

        result = PostgresReadOnlyQueryResult(
            tool_call_id=tool_call_id,
            rows=exposed_rows,
            row_count=len(exposed_rows),
            truncated=len(exposed_rows) >= params.limit,
            columns=None,
            query_fingerprint=query_fingerprint,
            evidence=evidence,
        )

        if _force_output_contract_violation_enabled():
            output_payload = result.model_dump(by_alias=True)
            output_payload["rowCount"] = "__invalid__"
            return output_payload

        return result
