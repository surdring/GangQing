from __future__ import annotations

import pytest

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.schemas.intent import IntentResult, IntentType, RiskLevel
from gangqing.tools.gate import assert_tool_call_allowed
from gangqing.tools.registry import build_default_registry


def _make_intent(*, intent: IntentType, has_write_intent: bool = False) -> IntentResult:
    return IntentResult(
        intent=intent,
        confidence=0.9,
        needsClarification=False,
        clarificationQuestions=[],
        reasonCodes=["test"],
        reasonSummary=None,
        hasWriteIntent=has_write_intent,
        riskLevel=RiskLevel.LOW,
    )


def test_gate_blocks_action_intent_with_guardrail() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager", stepId="s1")
    registry = build_default_registry()
    intent = _make_intent(intent=IntentType.ACTION_EXECUTE, has_write_intent=True)

    with pytest.raises(AppError) as e:
        assert_tool_call_allowed(
            ctx=ctx,
            intent_result=intent,
            registry=registry,
            tool_name="postgres_readonly_query",
            tool_call_id="tc1",
            raw_params_summary={"tenantId": "t1", "projectId": "p1"},
            audit_fn=lambda **_: None,
        )

    assert e.value.code == ErrorCode.GUARDRAIL_BLOCKED


def test_gate_blocks_cross_scope_params_with_auth_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager", stepId="s1")
    registry = build_default_registry()
    intent = _make_intent(intent=IntentType.QUERY, has_write_intent=False)

    with pytest.raises(AppError) as e:
        assert_tool_call_allowed(
            ctx=ctx,
            intent_result=intent,
            registry=registry,
            tool_name="postgres_readonly_query",
            tool_call_id="tc1",
            raw_params_summary={"tenantId": "t2", "projectId": "p1"},
            audit_fn=lambda **_: None,
        )

    assert e.value.code == ErrorCode.AUTH_ERROR


def test_gate_blocks_missing_capability_with_forbidden() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="dispatcher", stepId="s1")
    registry = build_default_registry()
    intent = _make_intent(intent=IntentType.QUERY, has_write_intent=False)

    with pytest.raises(AppError) as e:
        assert_tool_call_allowed(
            ctx=ctx,
            intent_result=intent,
            registry=registry,
            tool_name="postgres_readonly_query",
            tool_call_id="tc1",
            raw_params_summary={"tenantId": "t1", "projectId": "p1"},
            audit_fn=lambda **_: None,
        )

    assert e.value.code == ErrorCode.FORBIDDEN


def test_gate_blocks_unknown_tool_with_forbidden() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager", stepId="s1")
    registry = build_default_registry()
    intent = _make_intent(intent=IntentType.QUERY, has_write_intent=False)

    with pytest.raises(AppError) as e:
        assert_tool_call_allowed(
            ctx=ctx,
            intent_result=intent,
            registry=registry,
            tool_name="not_a_real_tool",
            tool_call_id="tc1",
            raw_params_summary={"tenantId": "t1", "projectId": "p1"},
            audit_fn=lambda **_: None,
        )

    assert e.value.code == ErrorCode.FORBIDDEN
