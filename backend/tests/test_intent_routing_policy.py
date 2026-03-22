from __future__ import annotations

import pytest

from gangqing.agent.routing import ToolSpec, route_intent
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.schemas.intent import ClarificationQuestion, IntentResult, IntentType, RiskLevel


def _ctx(*, role: str) -> RequestContext:
    return RequestContext(
        requestId="req_test_route_1",
        tenantId="tenant_test",
        projectId="project_test",
        sessionId="session_test",
        userId="user_test",
        role=role,
        taskId=None,
        stepId=None,
    )


def _intent_result(*, intent: IntentType, needs_clarification: bool) -> IntentResult:
    questions = (
        [ClarificationQuestion(questionId="q1", question="Please clarify")]
        if needs_clarification
        else []
    )
    return IntentResult(
        intent=intent,
        confidence=0.9,
        needsClarification=needs_clarification,
        clarificationQuestions=questions,
        reasonCodes=["UNIT_TEST"],
        reasonSummary=None,
        hasWriteIntent=needs_clarification or intent in {IntentType.ACTION_PREPARE, IntentType.ACTION_EXECUTE},
        riskLevel=RiskLevel.MEDIUM
        if needs_clarification or intent == IntentType.ACTION_PREPARE
        else (RiskLevel.HIGH if intent == IntentType.ACTION_EXECUTE else RiskLevel.LOW),
    )


def test_route_action_execute_blocked_guardrail() -> None:
    ctx = _ctx(role="plant_manager")
    intent_result = _intent_result(intent=IntentType.ACTION_EXECUTE, needs_clarification=False)
    decision = route_intent(ctx=ctx, intent_result=intent_result, tool_specs=[])

    assert decision.decision_type.value == "block"
    assert decision.blocked_reason_code == ErrorCode.GUARDRAIL_BLOCKED.value
    assert decision.selected_intent == IntentType.ACTION_EXECUTE


def test_route_forbidden_when_missing_tool_capability() -> None:
    ctx = _ctx(role="dispatcher")

    tool_specs = [
        ToolSpec(name="postgres_readonly_query", requiredCapability="tool:postgres:read"),
    ]

    intent_result = _intent_result(intent=IntentType.QUERY, needs_clarification=False)
    with pytest.raises(AppError) as err:
        route_intent(ctx=ctx, intent_result=intent_result, tool_specs=tool_specs)

    assert err.value.code == ErrorCode.FORBIDDEN
    assert err.value.message == "Forbidden"

    payload = err.value.to_response().model_dump(by_alias=True)
    for key in ["code", "message", "details", "retryable", "requestId"]:
        assert key in payload
    assert payload["code"] == ErrorCode.FORBIDDEN.value
    assert payload["requestId"] == ctx.request_id
    assert payload["retryable"] is False


def test_route_action_prepare_returns_draft() -> None:
    ctx = _ctx(role="viewer")
    intent_result = _intent_result(intent=IntentType.ACTION_PREPARE, needs_clarification=False)
    decision = route_intent(ctx=ctx, intent_result=intent_result, tool_specs=[])

    assert decision.decision_type.value == "draft"
    assert decision.draft is not None
    assert decision.draft.draft_id


def test_route_needs_clarification_returns_clarify() -> None:
    ctx = _ctx(role="viewer")
    intent_result = _intent_result(intent=IntentType.QUERY, needs_clarification=True)
    decision = route_intent(ctx=ctx, intent_result=intent_result, tool_specs=[])

    assert decision.decision_type.value == "clarify"
    assert decision.clarification
