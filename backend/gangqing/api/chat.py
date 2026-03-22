from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gangqing.common.auth import require_authed_request_context
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode, ErrorResponse
from gangqing.common.rbac import require_capability
from gangqing.agent.intent import identify_intent
from gangqing.agent.routing import ToolSpec, route_intent
from gangqing.common.settings import load_settings
from gangqing.tools.registry import build_default_registry
from gangqing.common.evidence_degradation import evaluate_evidence_degradation
from gangqing.common.guardrail.engine import build_input_digest
from gangqing.common.guardrail.engine import build_guardrail_evidence
from gangqing.common.guardrail.engine import decision_to_app_error
from gangqing.common.guardrail.engine import evaluate_text
from gangqing.common.guardrail.engine import write_guardrail_audit
from gangqing.schemas.guardrail import GuardrailAction
from gangqing.schemas.guardrail import GuardrailHitLocation
from gangqing.schemas.sse import (
    SseEvent,
    SseEvidenceUpdateEvent,
    SseFinalEvent,
    SseMessageDeltaEvent,
    SseProgressEvent,
    SseToolCallEvent,
    SseToolResultEvent,
    SseWarningEvent,
    build_error_envelope,
    build_meta_envelope,
)
from gangqing.tools.postgres_readonly import PostgresReadOnlyQueryTool
from gangqing.tools.gate import assert_tool_call_allowed
from gangqing.common.cancellation import CancellationScope, cancellation_registry
from gangqing_db.draft import insert_draft
from gangqing_db.evidence import Evidence
from gangqing_db.evidence_chain import EvidenceWarning
from gangqing_db.evidence_store import upsert_evidence


router = APIRouter()


_EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_\-\.]{0,127}$")


def _is_valid_evidence_id(value: str) -> bool:
    s = (value or "").strip()
    if not s:
        return False
    return _EVIDENCE_ID_RE.match(s) is not None


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatStreamCancelRequest(BaseModel):
    request_id: str = Field(min_length=1, alias="requestId")

    model_config = {"populate_by_name": True}


@router.post("/chat/stream/cancel")
async def chat_stream_cancel(
    payload: ChatStreamCancelRequest,
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("chat:conversation:stream")),
) -> dict:
    request_id = (payload.request_id or "").strip()
    if not request_id:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Missing requestId",
            request_id=ctx.request_id,
            details={"field": "requestId"},
            retryable=False,
        )

    cancellation_registry.cancel(
        caller_scope=CancellationScope(tenant_id=ctx.tenant_id, project_id=ctx.project_id),
        request_id=request_id,
    )
    return {"status": "ok"}


def _encode_sse_event(event: SseEvent) -> str:
    data = json.dumps(event.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
    if "\n" in data or "\r" in data:
        raise RuntimeError("SSE event data must be a single-line JSON")
    return f"event: {event.type}\ndata: {data}\n\n"


def _emit_cancelled_final(*, ctx: RequestContext, sequence: int) -> tuple[list[str], int]:
    chunks: list[str] = []
    chunks.append(
        _encode_sse_event(
            SseFinalEvent(
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload={"status": "cancelled"},
            )
        )
    )
    sequence += 1
    return chunks, sequence


def _emit_error_and_final(*, ctx: RequestContext, sequence: int, error: AppError) -> tuple[list[str], int]:
    chunks: list[str] = []

    chunks.append(
        _encode_sse_event(
            build_error_envelope(
                ctx=ctx,
                sequence=sequence,
                timestamp=datetime.now(timezone.utc),
                payload=ErrorResponse.model_validate(_build_error_payload(ctx=ctx, error=error)),
            )
        )
    )
    sequence += 1
    chunks.append(
        _encode_sse_event(
            SseFinalEvent(
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload={"status": "error"},
            )
        )
    )
    sequence += 1
    return chunks, sequence


def _build_error_payload(*, ctx: RequestContext, error: AppError | None) -> dict:
    if error is not None:
        payload = error.to_response().model_dump(by_alias=True)
    else:
        payload = ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR.value,
            message="Internal error",
            details=None,
            retryable=False,
            request_id=ctx.request_id,
        ).model_dump(by_alias=True)

    validated = ErrorResponse.model_validate(payload)
    return validated.model_dump(by_alias=True)


def _build_minimal_error_response(
    *,
    ctx: RequestContext,
    code: str,
    retryable: bool,
) -> dict:
    message_map = {
        ErrorCode.UPSTREAM_TIMEOUT.value: "Upstream request timed out",
        ErrorCode.UPSTREAM_UNAVAILABLE.value: "Upstream service is unavailable",
        ErrorCode.CONTRACT_VIOLATION.value: "Contract violation",
        ErrorCode.VALIDATION_ERROR.value: "Validation failed",
        ErrorCode.FORBIDDEN.value: "Forbidden",
        ErrorCode.AUTH_ERROR.value: "Unauthorized",
        ErrorCode.INTERNAL_ERROR.value: "Internal error",
    }

    payload = ErrorResponse(
        code=code,
        message=str(message_map.get(code, "Internal error")),
        details=None,
        retryable=bool(retryable),
        request_id=ctx.request_id,
    ).model_dump(by_alias=True)
    validated = ErrorResponse.model_validate(payload)
    return validated.model_dump(by_alias=True)


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    payload: ChatStreamRequest,
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("chat:conversation:stream")),
) -> StreamingResponse:
    async def _gen():
        sequence = 1
        now = datetime.now(timezone.utc)
        yield _encode_sse_event(build_meta_envelope(ctx=ctx, sequence=sequence, timestamp=now))
        sequence += 1

        seen_evidence_ids: set[str] = set()

        tool_call_id: str | None = None
        input_digest = build_input_digest(payload.message)
        output_degraded = False

        cancel_event = cancellation_registry.register(
            request_id=ctx.request_id,
            scope=CancellationScope(tenant_id=ctx.tenant_id, project_id=ctx.project_id),
        )

        async def _watch_disconnect() -> None:
            while not cancel_event.is_set():
                if await request.is_disconnected():
                    cancel_event.set()
                    return
                await asyncio.sleep(0.05)

        watcher = asyncio.create_task(_watch_disconnect())

        try:
            if cancel_event.is_set() or await request.is_disconnected():
                cancel_event.set()
                watcher.cancel()
                if not await request.is_disconnected():
                    chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                    for chunk in chunks:
                        yield chunk
                return

            input_decision = evaluate_text(
                hit_location=GuardrailHitLocation.INPUT,
                text=payload.message,
            )
            if input_decision.action != GuardrailAction.ALLOW:
                guardrail_ev = build_guardrail_evidence(
                    ctx=ctx,
                    stage="guardrail.input",
                    decision=input_decision,
                )
                try:
                    upsert_evidence(
                        ctx=ctx,
                        request_id=ctx.request_id,
                        evidence=guardrail_ev,
                        mode="append",
                    )
                except Exception:
                    guardrail_ev = guardrail_ev
                if guardrail_ev.evidence_id not in seen_evidence_ids:
                    seen_evidence_ids.add(guardrail_ev.evidence_id)
                    yield _encode_sse_event(
                        SseEvidenceUpdateEvent(
                            timestamp=datetime.now(timezone.utc),
                            request_id=ctx.request_id,
                            tenant_id=ctx.tenant_id,
                            project_id=ctx.project_id,
                            session_id=ctx.session_id,
                            sequence=sequence,
                            payload={
                                "mode": "append",
                                "evidences": [guardrail_ev],
                                "evidenceIds": None,
                            },
                        )
                    )
                    sequence += 1

                write_guardrail_audit(
                    ctx=ctx,
                    stage="guardrail.input",
                    decision=input_decision,
                    input_digest=input_digest,
                    evidence_refs=[guardrail_ev.evidence_id],
                    result_status="failure"
                    if input_decision.action
                    in {GuardrailAction.BLOCK_FORBIDDEN, GuardrailAction.BLOCK_GUARDRAIL}
                    else "success",
                )
                if input_decision.action in {
                    GuardrailAction.BLOCK_FORBIDDEN,
                    GuardrailAction.BLOCK_GUARDRAIL,
                }:
                    err = decision_to_app_error(ctx=ctx, stage="guardrail.input", decision=input_decision)
                    chunks, sequence = _emit_error_and_final(ctx=ctx, sequence=sequence, error=err)
                    for chunk in chunks:
                        yield chunk
                    cancel_event.set()
                    watcher.cancel()
                    return

                yield _encode_sse_event(
                    SseWarningEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={
                            "code": ErrorCode.GUARDRAIL_BLOCKED.value,
                            "message": "Guardrail warning: request will be degraded",
                            "details": {
                                "stage": "guardrail.input",
                                "inputDigest": {
                                    "sha256": input_digest.sha256,
                                    "length": input_digest.length,
                                },
                                "hits": [h.model_dump(by_alias=True) for h in input_decision.hits],
                                "evidenceRefs": [guardrail_ev.evidence_id],
                            },
                        },
                    )
                )
                sequence += 1
                output_degraded = True

            intent_result = identify_intent(ctx=ctx, text=payload.message)
            if cancel_event.is_set() or await request.is_disconnected():
                cancel_event.set()
                watcher.cancel()
                if not await request.is_disconnected():
                    chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                    for chunk in chunks:
                        yield chunk
                return
            yield _encode_sse_event(
                SseEvent(
                    type="intent.result",
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload=intent_result.model_dump(by_alias=True),
                )
            )
            sequence += 1

            registry = build_default_registry()
            tool_specs = [
                ToolSpec.model_validate(spec.model_dump(by_alias=True))
                for spec in registry.build_tool_specs_for_routing()
            ]

            route_decision = route_intent(ctx=ctx, intent_result=intent_result, tool_specs=tool_specs)
            if cancel_event.is_set() or await request.is_disconnected():
                cancel_event.set()
                watcher.cancel()
                if not await request.is_disconnected():
                    chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                    for chunk in chunks:
                        yield chunk
                return
            yield _encode_sse_event(
                SseEvent(
                    type="routing.decision",
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload=route_decision.model_dump(by_alias=True),
                )
            )
            sequence += 1

            if route_decision.decision_type.value == "clarify":
                yield _encode_sse_event(
                    SseFinalEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={"status": "success"},
                    )
                )
                sequence += 1
                cancel_event.set()
                watcher.cancel()
                return

            if route_decision.decision_type.value == "block":
                err = AppError(
                    ErrorCode.GUARDRAIL_BLOCKED,
                    "Write intent blocked by read-only default policy",
                    request_id=ctx.request_id,
                    details={
                        "stage": "chat.intent_routing",
                        "intent": intent_result.intent.value,
                    },
                    retryable=False,
                )
                yield _encode_sse_event(
                    build_error_envelope(
                        ctx=ctx,
                        sequence=sequence,
                        timestamp=datetime.now(timezone.utc),
                        payload=ErrorResponse.model_validate(_build_error_payload(ctx=ctx, error=err)),
                    )
                )
                sequence += 1
                yield _encode_sse_event(
                    SseFinalEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={"status": "error"},
                    )
                )
                sequence += 1
                return

            if route_decision.decision_type.value == "draft":
                if route_decision.draft is not None:
                    try:
                        insert_draft(
                            draft_id=route_decision.draft.draft_id,
                            payload=route_decision.draft.model_dump(by_alias=True),
                            ctx=ctx,
                        )
                    except Exception as e:
                        err = AppError(
                            ErrorCode.UPSTREAM_UNAVAILABLE,
                            "Upstream service is unavailable",
                            request_id=ctx.request_id,
                            details={
                                "stage": "draft.persistence",
                                "error": "draft persistence failed",
                            },
                            retryable=True,
                        )
                        yield _encode_sse_event(
                            build_error_envelope(
                                ctx=ctx,
                                sequence=sequence,
                                timestamp=datetime.now(timezone.utc),
                                payload=ErrorResponse.model_validate(
                                    _build_error_payload(ctx=ctx, error=err)
                                ),
                            )
                        )
                        sequence += 1
                        yield _encode_sse_event(
                            SseFinalEvent(
                                timestamp=datetime.now(timezone.utc),
                                request_id=ctx.request_id,
                                tenant_id=ctx.tenant_id,
                                project_id=ctx.project_id,
                                session_id=ctx.session_id,
                                sequence=sequence,
                                payload={"status": "error"},
                            )
                        )
                        sequence += 1
                        cancel_event.set()
                        watcher.cancel()
                        cancellation_registry.unregister(request_id=ctx.request_id)
                        return

                    yield _encode_sse_event(
                        SseEvent(
                            type="draft.created",
                            timestamp=datetime.now(timezone.utc),
                            request_id=ctx.request_id,
                            tenant_id=ctx.tenant_id,
                            project_id=ctx.project_id,
                            session_id=ctx.session_id,
                            sequence=sequence,
                            payload=route_decision.draft.model_dump(by_alias=True),
                        )
                    )
                    sequence += 1

                yield _encode_sse_event(
                    SseFinalEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={"status": "success"},
                    )
                )
                sequence += 1
                return

            if "postgres_readonly_query" not in set(route_decision.allowed_tool_names or []):
                yield _encode_sse_event(
                    SseProgressEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={
                            "stage": "tooling",
                            "message": "No tools allowed by policy",
                        },
                    )
                )
                sequence += 1
                yield _encode_sse_event(
                    SseFinalEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={"status": "success"},
                    )
                )
                sequence += 1
                return

            yield _encode_sse_event(
                SseProgressEvent(
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={"stage": "tooling", "message": "Starting tool execution"},
                )
            )
            sequence += 1

            loop = asyncio.get_running_loop()
            retry_events: asyncio.Queue[dict] = asyncio.Queue()

            def _emit_retry_event(evt: dict) -> None:
                loop.call_soon_threadsafe(retry_events.put_nowait, evt)

            tool = PostgresReadOnlyQueryTool()
            tool_call_id = uuid.uuid4().hex

            if cancel_event.is_set() or await request.is_disconnected():
                cancel_event.set()
                watcher.cancel()
                if not await request.is_disconnected():
                    chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                    for chunk in chunks:
                        yield chunk
                return

            now_dt = datetime.now(timezone.utc)
            start_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now_dt

            args_summary = {
                "templateId": "production_daily_slow"
                if "slow" in payload.message.lower()
                else "production_daily",
                "timeRange": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "limit": 10,
                "offset": 0,
                "timeoutSeconds": 0.001
                if "timeout" in payload.message.lower()
                else (0.05 if "slow" in payload.message.lower() else None),
            }

            try:
                assert_tool_call_allowed(
                    ctx=ctx,
                    intent_result=intent_result,
                    registry=registry,
                    tool_name=tool.name,
                    tool_call_id=tool_call_id,
                    raw_params_summary=args_summary,
                )
            except AppError as e:
                chunks, sequence = _emit_error_and_final(ctx=ctx, sequence=sequence, error=e)
                for chunk in chunks:
                    yield chunk
                cancel_event.set()
                watcher.cancel()
                return

            yield _encode_sse_event(
                SseToolCallEvent(
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={
                        "toolCallId": tool_call_id,
                        "toolName": tool.name,
                        "argsSummary": {
                            **args_summary,
                            "retry": {"attempt": 1, "maxAttempts": int(load_settings().tool_max_retries) + 1},
                        },
                    },
                )
            )
            sequence += 1

            async def _run_tool_in_thread():
                def _run() -> object:
                    try:
                        return tool.run_raw(
                            ctx=ctx,
                            raw_params={
                                "toolCallId": tool_call_id,
                                "templateId": "production_daily_slow"
                                if "slow" in payload.message.lower()
                                else "production_daily",
                                "timeRange": {
                                    "start": start_dt,
                                    "end": end_dt,
                                },
                                "timeoutSeconds": args_summary.get("timeoutSeconds"),
                                "limit": 10,
                                "offset": 0,
                            },
                            retry_observer=_emit_retry_event,
                            should_cancel=cancel_event.is_set,
                        )
                    finally:
                        _emit_retry_event({"type": "tool_done", "toolName": tool.name})

                return await asyncio.to_thread(_run)

            tool_task = asyncio.create_task(_run_tool_in_thread())

            async def _drain_retry_events() -> AsyncIterator[str]:
                nonlocal sequence
                tool_done_seen = False
                while True:
                    if cancel_event.is_set() or await request.is_disconnected():
                        cancel_event.set()
                        return
                    if tool_done_seen and retry_events.empty():
                        if tool_task.done():
                            return
                        await asyncio.sleep(0.01)
                        continue
                    try:
                        evt = await asyncio.wait_for(retry_events.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        if tool_done_seen and tool_task.done() and retry_events.empty():
                            return
                        continue

                    evt_type = str(evt.get("type") or "")
                    tool_name = str(evt.get("toolName") or "")
                    attempt = int(evt.get("attempt") or 0)
                    max_attempts = int(evt.get("maxAttempts") or 0)

                    if evt_type == "tool_done":
                        tool_done_seen = True
                        continue

                    if evt_type == "attempt_start":
                        if attempt <= 1:
                            continue
                        if cancel_event.is_set() or await request.is_disconnected():
                            cancel_event.set()
                            return
                        yield _encode_sse_event(
                            SseToolCallEvent(
                                timestamp=datetime.now(timezone.utc),
                                request_id=ctx.request_id,
                                tenant_id=ctx.tenant_id,
                                project_id=ctx.project_id,
                                session_id=ctx.session_id,
                                sequence=sequence,
                                payload={
                                    "toolCallId": tool_call_id,
                                    "toolName": tool_name,
                                    "argsSummary": {
                                        **args_summary,
                                        "retry": {
                                            "attempt": attempt,
                                            "maxAttempts": max_attempts,
                                        },
                                    },
                                },
                            )
                        )
                        sequence += 1
                        continue

                    if evt_type == "attempt_failure":
                        continue

                    if evt_type == "retry_scheduled":
                        backoff_ms = int(evt.get("backoffMs") or 0)
                        reason_code = str(evt.get("reasonCode") or "")
                        if cancel_event.is_set() or await request.is_disconnected():
                            cancel_event.set()
                            return
                        yield _encode_sse_event(
                            SseProgressEvent(
                                timestamp=datetime.now(timezone.utc),
                                request_id=ctx.request_id,
                                tenant_id=ctx.tenant_id,
                                project_id=ctx.project_id,
                                session_id=ctx.session_id,
                                sequence=sequence,
                                payload={
                                    "stage": "tooling.backoff",
                                    "message": "Waiting before retry",
                                    "details": {
                                        "toolName": tool_name,
                                        "attempt": attempt,
                                        "maxAttempts": max_attempts,
                                        "backoffMs": backoff_ms,
                                        "reasonCode": reason_code,
                                    },
                                },
                            )
                        )
                        sequence += 1
                        yield _encode_sse_event(
                            SseWarningEvent(
                                timestamp=datetime.now(timezone.utc),
                                request_id=ctx.request_id,
                                tenant_id=ctx.tenant_id,
                                project_id=ctx.project_id,
                                session_id=ctx.session_id,
                                sequence=sequence,
                                payload={
                                    "code": reason_code or ErrorCode.UPSTREAM_TIMEOUT.value,
                                    "message": "Tool attempt failed; retry scheduled",
                                    "details": {
                                        "toolName": tool_name,
                                        "attempt": attempt,
                                        "maxAttempts": max_attempts,
                                        "backoffMs": backoff_ms,
                                        "reasonCode": reason_code,
                                    },
                                },
                            )
                        )
                        sequence += 1
                        continue

                    if evt_type == "attempt_success":
                        continue

            async for chunk in _drain_retry_events():
                yield chunk

            try:
                result = await tool_task
            finally:
                watcher.cancel()

            if cancel_event.is_set() or await request.is_disconnected():
                cancel_event.set()
                if not await request.is_disconnected():
                    chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                    for chunk in chunks:
                        yield chunk
                return

            evidence_refs: list[str] | None = None
            result_summary: dict | None = None
            evidence_updates: list[Evidence] = []
            if result is not None:
                if hasattr(result, "model_dump"):
                    dumped = result.model_dump(by_alias=True)
                elif isinstance(result, dict):
                    dumped = result
                else:
                    dumped = None

                if isinstance(dumped, dict):
                    try:
                        context_text = json.dumps(
                            dumped,
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        )
                    except Exception:
                        context_text = str(dumped)

                    context_decision = evaluate_text(
                        hit_location=GuardrailHitLocation.TOOL_CONTEXT,
                        text=context_text,
                    )
                    if context_decision.action != GuardrailAction.ALLOW:
                        guardrail_ev = build_guardrail_evidence(
                            ctx=ctx,
                            stage="guardrail.tool_context",
                            decision=context_decision,
                        )
                        try:
                            upsert_evidence(
                                ctx=ctx,
                                request_id=ctx.request_id,
                                evidence=guardrail_ev,
                                mode="append",
                            )
                        except Exception:
                            guardrail_ev = guardrail_ev
                        if guardrail_ev.evidence_id not in seen_evidence_ids:
                            seen_evidence_ids.add(guardrail_ev.evidence_id)
                            yield _encode_sse_event(
                                SseEvidenceUpdateEvent(
                                    timestamp=datetime.now(timezone.utc),
                                    request_id=ctx.request_id,
                                    tenant_id=ctx.tenant_id,
                                    project_id=ctx.project_id,
                                    session_id=ctx.session_id,
                                    sequence=sequence,
                                    payload={
                                        "mode": "append",
                                        "evidences": [guardrail_ev],
                                        "evidenceIds": None,
                                    },
                                )
                            )
                            sequence += 1

                        write_guardrail_audit(
                            ctx=ctx,
                            stage="guardrail.tool_context",
                            decision=context_decision,
                            input_digest=None,
                            evidence_refs=[guardrail_ev.evidence_id],
                            extra_action_summary={
                                "toolName": tool.name,
                                "toolCallId": tool_call_id,
                            },
                            result_status="failure"
                            if context_decision.action
                            in {GuardrailAction.BLOCK_FORBIDDEN, GuardrailAction.BLOCK_GUARDRAIL}
                            else "success",
                        )
                        if context_decision.action in {
                            GuardrailAction.BLOCK_FORBIDDEN,
                            GuardrailAction.BLOCK_GUARDRAIL,
                        }:
                            err = decision_to_app_error(
                                ctx=ctx,
                                stage="guardrail.tool_context",
                                decision=context_decision,
                            )
                            chunks, sequence = _emit_error_and_final(ctx=ctx, sequence=sequence, error=err)
                            for chunk in chunks:
                                yield chunk
                            cancel_event.set()
                            watcher.cancel()
                            return

                        yield _encode_sse_event(
                            SseWarningEvent(
                                timestamp=datetime.now(timezone.utc),
                                request_id=ctx.request_id,
                                tenant_id=ctx.tenant_id,
                                project_id=ctx.project_id,
                                session_id=ctx.session_id,
                                sequence=sequence,
                                payload={
                                    "code": ErrorCode.GUARDRAIL_BLOCKED.value,
                                    "message": "Guardrail warning: response will be degraded",
                                    "details": {
                                        "stage": "guardrail.tool_context",
                                        "hits": [
                                            h.model_dump(by_alias=True) for h in context_decision.hits
                                        ],
                                        "evidenceRefs": [guardrail_ev.evidence_id],
                                    },
                                },
                            )
                        )
                        sequence += 1
                        output_degraded = True

                    candidate_ids: list[str] = []
                    evidence = dumped.get("evidence")
                    if isinstance(evidence, dict) and isinstance(evidence.get("evidenceId"), str):
                        candidate_ids.append(str(evidence.get("evidenceId")))
                        evidence_updates.append(Evidence.model_validate(evidence))
                    evidence_list = dumped.get("evidences")
                    if isinstance(evidence_list, list):
                        for item in evidence_list:
                            if isinstance(item, dict) and isinstance(item.get("evidenceId"), str):
                                candidate_ids.append(str(item.get("evidenceId")))
                                evidence_updates.append(Evidence.model_validate(item))

                    unique_evidence_updates: dict[str, Evidence] = {}
                    for ev in evidence_updates:
                        unique_evidence_updates[ev.evidence_id] = ev
                    evidence_updates = [
                        unique_evidence_updates[eid] for eid in sorted(unique_evidence_updates.keys())
                    ]

                    valid_ids: list[str] = []
                    for eid in candidate_ids:
                        if _is_valid_evidence_id(eid):
                            valid_ids.append(eid)
                    if valid_ids:
                        evidence_refs = sorted(set(valid_ids))
                    result_summary = {
                        "toolName": tool.name,
                        "rowCount": dumped.get("rowCount"),
                        "truncated": dumped.get("truncated"),
                    }

            if evidence_updates:
                append_evidences: list[Evidence] = []
                update_evidences: list[Evidence] = []
                for ev in evidence_updates:
                    if ev.evidence_id in seen_evidence_ids:
                        update_evidences.append(ev)
                    else:
                        append_evidences.append(ev)

                def _persist_batch(*, mode: str, evidences: list[Evidence]) -> list[EvidenceWarning]:
                    merge_warnings: list[EvidenceWarning] = []
                    for ev in evidences:
                        try:
                            merge_warnings.extend(
                                upsert_evidence(
                                    ctx=ctx,
                                    request_id=ctx.request_id,
                                    evidence=ev,
                                    mode=mode,
                                )
                            )
                        except Exception:
                            pass
                    return merge_warnings

                if append_evidences:
                    _persist_batch(mode="append", evidences=append_evidences)
                    for ev in append_evidences:
                        seen_evidence_ids.add(ev.evidence_id)
                    yield _encode_sse_event(
                        SseEvidenceUpdateEvent(
                            timestamp=datetime.now(timezone.utc),
                            request_id=ctx.request_id,
                            tenant_id=ctx.tenant_id,
                            project_id=ctx.project_id,
                            session_id=ctx.session_id,
                            sequence=sequence,
                            payload={
                                "mode": "append",
                                "evidences": append_evidences,
                                "evidenceIds": None,
                            },
                        )
                    )
                    sequence += 1

                if update_evidences:
                    merge_warnings = _persist_batch(mode="update", evidences=update_evidences)
                    for ev in update_evidences:
                        seen_evidence_ids.add(ev.evidence_id)
                    yield _encode_sse_event(
                        SseEvidenceUpdateEvent(
                            timestamp=datetime.now(timezone.utc),
                            request_id=ctx.request_id,
                            tenant_id=ctx.tenant_id,
                            project_id=ctx.project_id,
                            session_id=ctx.session_id,
                            sequence=sequence,
                            payload={
                                "mode": "update",
                                "evidences": update_evidences,
                                "evidenceIds": None,
                            },
                        )
                    )
                    sequence += 1

                    for w in merge_warnings:
                        yield _encode_sse_event(
                            SseWarningEvent(
                                timestamp=datetime.now(timezone.utc),
                                request_id=ctx.request_id,
                                tenant_id=ctx.tenant_id,
                                project_id=ctx.project_id,
                                session_id=ctx.session_id,
                                sequence=sequence,
                                payload={
                                    "code": w.code,
                                    "message": w.message,
                                    "details": w.details,
                                },
                            )
                        )
                        sequence += 1

            degradation = evaluate_evidence_degradation(
                tool_call_id=tool_call_id,
                tool_name=tool.name,
                evidence_refs=evidence_refs,
                evidences=evidence_updates,
            )
            for w in degradation.warnings:
                yield _encode_sse_event(
                    SseWarningEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={
                            "code": w.code,
                            "message": w.message,
                            "details": w.details,
                        },
                    )
                )
                sequence += 1

            yield _encode_sse_event(
                SseToolResultEvent(
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={
                        "toolCallId": tool_call_id,
                        "toolName": tool.name,
                        "status": "success",
                        "resultSummary": result_summary or {"toolName": tool.name},
                        "error": None,
                        "evidenceRefs": evidence_refs,
                    },
                )
            )
            sequence += 1

            yield _encode_sse_event(
                SseProgressEvent(
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={
                        "stage": "tooling",
                        "message": "Tool execution completed",
                    },
                )
            )
            sequence += 1

            delta_text = (
                "已触发安全策略，回答已降级为仅展示数据与来源。" if output_degraded else "Done."
            )
            output_decision = evaluate_text(
                hit_location=GuardrailHitLocation.OUTPUT,
                text=delta_text,
            )
            if output_decision.action != GuardrailAction.ALLOW:
                guardrail_ev = build_guardrail_evidence(
                    ctx=ctx,
                    stage="guardrail.output",
                    decision=output_decision,
                )
                try:
                    upsert_evidence(
                        ctx=ctx,
                        request_id=ctx.request_id,
                        evidence=guardrail_ev,
                        mode="append",
                    )
                except Exception:
                    guardrail_ev = guardrail_ev
                if guardrail_ev.evidence_id not in seen_evidence_ids:
                    seen_evidence_ids.add(guardrail_ev.evidence_id)
                    yield _encode_sse_event(
                        SseEvidenceUpdateEvent(
                            timestamp=datetime.now(timezone.utc),
                            request_id=ctx.request_id,
                            tenant_id=ctx.tenant_id,
                            project_id=ctx.project_id,
                            session_id=ctx.session_id,
                            sequence=sequence,
                            payload={
                                "mode": "append",
                                "evidences": [guardrail_ev],
                                "evidenceIds": None,
                            },
                        )
                    )
                    sequence += 1

                write_guardrail_audit(
                    ctx=ctx,
                    stage="guardrail.output",
                    decision=output_decision,
                    input_digest=None,
                    evidence_refs=[guardrail_ev.evidence_id],
                    result_status="failure"
                    if output_decision.action
                    in {GuardrailAction.BLOCK_FORBIDDEN, GuardrailAction.BLOCK_GUARDRAIL}
                    else "success",
                )
                if output_decision.action in {
                    GuardrailAction.BLOCK_FORBIDDEN,
                    GuardrailAction.BLOCK_GUARDRAIL,
                }:
                    err = decision_to_app_error(
                        ctx=ctx,
                        stage="guardrail.output",
                        decision=output_decision,
                    )
                    chunks, sequence = _emit_error_and_final(ctx=ctx, sequence=sequence, error=err)
                    for chunk in chunks:
                        yield chunk
                    cancel_event.set()
                    watcher.cancel()
                    return

                yield _encode_sse_event(
                    SseWarningEvent(
                        timestamp=datetime.now(timezone.utc),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        session_id=ctx.session_id,
                        sequence=sequence,
                        payload={
                            "code": ErrorCode.GUARDRAIL_BLOCKED.value,
                            "message": "Guardrail warning: unsafe output filtered",
                            "details": {
                                "stage": "guardrail.output",
                                "hits": [h.model_dump(by_alias=True) for h in output_decision.hits],
                                "evidenceRefs": [guardrail_ev.evidence_id],
                            },
                        },
                    )
                )
                sequence += 1

                output_degraded = True
                delta_text = "已触发安全策略，回答已降级为仅展示数据与来源。"

            yield _encode_sse_event(
                SseMessageDeltaEvent(
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={"delta": delta_text},
                )
            )
            sequence += 1

            yield _encode_sse_event(
                SseFinalEvent(
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={"status": "success"},
                )
            )
            sequence += 1

        except AppError as e:
            if cancel_event.is_set() and not await request.is_disconnected():
                chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                for chunk in chunks:
                    yield chunk
                return

            chunks, sequence = _emit_error_and_final(ctx=ctx, sequence=sequence, error=e)
            for chunk in chunks:
                yield chunk
        except Exception:
            if cancel_event.is_set() and not await request.is_disconnected():
                chunks, sequence = _emit_cancelled_final(ctx=ctx, sequence=sequence)
                for chunk in chunks:
                    yield chunk
                return

            err = AppError(
                ErrorCode.INTERNAL_ERROR,
                "Internal error",
                request_id=ctx.request_id,
                details={"stage": "chat.stream"},
                retryable=False,
            )
            chunks, sequence = _emit_error_and_final(ctx=ctx, sequence=sequence, error=err)
            for chunk in chunks:
                yield chunk
        finally:
            cancel_event.set()
            watcher.cancel()
            cancellation_registry.unregister(request_id=ctx.request_id)

    return StreamingResponse(_gen(), media_type="text/event-stream")
