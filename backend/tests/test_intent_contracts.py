from __future__ import annotations

import pytest

from gangqing.schemas.intent import ClarificationQuestion, IntentResult, IntentType, RiskLevel
from gangqing.schemas.routing import ActionDraft, RouteDecision, RouteDecisionType


def test_intent_result_confidence_out_of_range_should_fail() -> None:
    with pytest.raises(Exception):
        IntentResult(
            intent=IntentType.QUERY,
            confidence=1.5,
            needsClarification=False,
            clarificationQuestions=[],
            reasonCodes=["UNIT_TEST"],
            reasonSummary=None,
            hasWriteIntent=False,
            riskLevel=RiskLevel.LOW,
        )


def test_intent_result_needs_clarification_requires_questions() -> None:
    with pytest.raises(Exception):
        IntentResult(
            intent=IntentType.QUERY,
            confidence=0.2,
            needsClarification=True,
            clarificationQuestions=[],
            reasonCodes=["UNIT_TEST"],
            reasonSummary=None,
            hasWriteIntent=True,
            riskLevel=RiskLevel.MEDIUM,
        )

    ok = IntentResult(
        intent=IntentType.QUERY,
        confidence=0.2,
        needsClarification=True,
        clarificationQuestions=[
            ClarificationQuestion(questionId="q1", question="Please clarify")
        ],
        reasonCodes=["UNIT_TEST"],
        reasonSummary=None,
        hasWriteIntent=True,
        riskLevel=RiskLevel.MEDIUM,
    )
    assert ok.needs_clarification is True


def test_route_decision_block_requires_reason_code() -> None:
    with pytest.raises(Exception):
        RouteDecision(
            decisionType=RouteDecisionType.BLOCK,
            selectedIntent=IntentType.ACTION_EXECUTE,
            allowedToolNames=[],
            blockedReasonCode=None,
            clarification=None,
            draft=None,
            auditTags={"k": "v"},
        )


def test_route_decision_clarify_requires_questions() -> None:
    with pytest.raises(Exception):
        RouteDecision(
            decisionType=RouteDecisionType.CLARIFY,
            selectedIntent=IntentType.QUERY,
            allowedToolNames=[],
            blockedReasonCode=None,
            clarification=None,
            draft=None,
            auditTags={"k": "v"},
        )


def test_route_decision_draft_requires_draft() -> None:
    with pytest.raises(Exception):
        RouteDecision(
            decisionType=RouteDecisionType.DRAFT,
            selectedIntent=IntentType.ACTION_PREPARE,
            allowedToolNames=[],
            blockedReasonCode=None,
            clarification=None,
            draft=None,
            auditTags={"k": "v"},
        )

    decision = RouteDecision(
        decisionType=RouteDecisionType.DRAFT,
        selectedIntent=IntentType.ACTION_PREPARE,
        allowedToolNames=[],
        blockedReasonCode=None,
        clarification=None,
        draft=ActionDraft(
            draftId="draft_1",
            actionType="unknown",
            targetResourceSummary="unknown",
            constraints=[],
            riskLevel=RiskLevel.MEDIUM,
            riskReasonCodes=["UNIT_TEST"],
            requiredCapabilities=[],
        ),
        auditTags={"k": "v"},
    )
    assert decision.decision_type == RouteDecisionType.DRAFT
