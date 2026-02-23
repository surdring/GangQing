from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gangqing.common.auth import require_authed_request_context
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode, ErrorResponse
from gangqing.common.rbac import require_capability
from gangqing.schemas.sse import SseEnvelope, build_meta_envelope


router = APIRouter()


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)


def _encode_sse_event(envelope: SseEnvelope) -> str:
    data = json.dumps(envelope.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
    return f"event: {envelope.type}\ndata: {data}\n\n"


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

        try:
            for i in range(3):
                if await request.is_disconnected():
                    return
                env = SseEnvelope(
                    type="progress",
                    timestamp=datetime.now(timezone.utc),
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    session_id=ctx.session_id,
                    sequence=sequence,
                    payload={"index": i, "content": f"echo:{payload.message}"},
                )
                yield _encode_sse_event(env)
                sequence += 1
                await asyncio.sleep(0)

            final_env = SseEnvelope(
                type="final",
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload={"done": True},
            )
            yield _encode_sse_event(final_env)

        except asyncio.CancelledError:
            raise
        except AppError as e:
            err_env = SseEnvelope(
                type="error",
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload=_build_error_payload(ctx=ctx, error=e),
            )
            yield _encode_sse_event(err_env)
            sequence += 1
            final_env = SseEnvelope(
                type="final",
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload={"done": True},
            )
            yield _encode_sse_event(final_env)
        except Exception:
            err_env = SseEnvelope(
                type="error",
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload=_build_error_payload(ctx=ctx, error=None),
            )
            yield _encode_sse_event(err_env)
            sequence += 1
            final_env = SseEnvelope(
                type="final",
                timestamp=datetime.now(timezone.utc),
                request_id=ctx.request_id,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                sequence=sequence,
                payload={"done": True},
            )
            yield _encode_sse_event(final_env)

    return StreamingResponse(_gen(), media_type="text/event-stream")
