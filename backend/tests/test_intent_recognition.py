from __future__ import annotations

from gangqing.agent.intent import IntentType, identify_intent
from gangqing.common.context import RequestContext


def _ctx() -> RequestContext:
    return RequestContext(
        requestId="req_test_1",
        tenantId="tenant_test",
        projectId="project_test",
        sessionId="session_test",
        userId="user_test",
        role="viewer",
        taskId=None,
        stepId=None,
    )


def test_intent_ambiguous_should_clarify() -> None:
    ctx = _ctx()
    result = identify_intent(ctx=ctx, text="帮我看一下")
    assert result.needs_clarification is True
    assert result.clarification_questions
    assert len(result.clarification_questions[0].question.strip()) > 0


def test_intent_query_confident() -> None:
    ctx = _ctx()
    result = identify_intent(ctx=ctx, text="查询今天产量数据")
    assert result.needs_clarification is False
    assert result.intent == IntentType.QUERY
    assert result.confidence >= 0.55


def test_intent_analyze_confident() -> None:
    ctx = _ctx()
    result = identify_intent(ctx=ctx, text="分析一下产量下降的原因，和上周对比")
    assert result.needs_clarification is False
    assert result.intent == IntentType.ANALYZE
    assert result.confidence >= 0.55
