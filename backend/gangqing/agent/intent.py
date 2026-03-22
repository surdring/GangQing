from __future__ import annotations

from typing import Any
import uuid

import structlog

from gangqing.common.audit import write_audit_event
from gangqing.common.context import RequestContext
from gangqing.schemas.intent import (
    ClarificationQuestion,
    IntentResult,
    IntentType,
    RiskLevel,
)


logger = structlog.get_logger(__name__)


_CLARIFY_INTENT = IntentType.QUERY


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _score_intents(text_norm: str) -> dict[IntentType, float]:
    scores: dict[IntentType, float] = {it: 0.0 for it in IntentType}

    query_keywords = [
        "query",
        "select",
        "slow",
        "查",
        "查询",
        "看看",
        "多少",
        "几",
        "列表",
        "明细",
        "报表",
        "数据",
        "show",
        "get",
        "list",
    ]
    analyze_keywords = [
        "analyze",
        "analysis",
        "原因",
        "为什么",
        "对比",
        "趋势",
        "预测",
        "评估",
        "优化",
        "diagnose",
        "root cause",
    ]
    alert_keywords = [
        "告警",
        "报警",
        "异常",
        "超限",
        "超标",
        "阈值",
        "alert",
        "alarm",
        "incident",
    ]
    action_prepare_keywords = [
        "准备",
        "草案",
        "方案",
        "建议",
        "计划",
        "步骤",
        "如何",
        "should we",
        "recommend",
        "proposal",
    ]
    action_execute_keywords = [
        "执行",
        "下发",
        "写入",
        "修改",
        "更新",
        "删除",
        "创建",
        "approve",
        "apply",
        "run",
        "execute",
    ]

    def _hit(keywords: list[str]) -> float:
        hit = 0
        for kw in keywords:
            if kw and kw in text_norm:
                hit += 1
        return float(hit)

    scores[IntentType.QUERY] += _hit(query_keywords) * 1.0
    scores[IntentType.ANALYZE] += _hit(analyze_keywords) * 1.2
    scores[IntentType.ALERT] += _hit(alert_keywords) * 1.3
    scores[IntentType.ACTION_PREPARE] += _hit(action_prepare_keywords) * 1.1
    scores[IntentType.ACTION_EXECUTE] += _hit(action_execute_keywords) * 1.4

    if any(x in text_norm for x in ["?", "？"]):
        scores[IntentType.QUERY] += 0.2
        scores[IntentType.ANALYZE] += 0.2

    if any(x in text_norm for x in ["please", "帮我", "帮忙", "麻烦"]):
        scores[IntentType.ACTION_PREPARE] += 0.1

    return scores


def _choose_intent(scores: dict[IntentType, float]) -> tuple[IntentType, float, float]:
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_intent, best_score = sorted_items[0]
    second_score = sorted_items[1][1] if len(sorted_items) > 1 else 0.0

    total = sum(scores.values())
    if total <= 0:
        return best_intent, 0.0, 0.0

    confidence = max(0.0, min(1.0, best_score / total))
    margin = best_score - second_score
    return best_intent, confidence, margin


def _build_clarification_question(text_norm: str) -> str:
    if not text_norm:
        return "请问你想查询数据、分析原因、查看告警，还是准备/执行某个操作？"

    if any(x in text_norm for x in ["异常", "告警", "报警", "alert", "alarm"]):
        return "你希望我查看哪一类告警（设备/产线/质量/能耗）？时间范围和对象（产线/设备）是什么？"

    if any(x in text_norm for x in ["原因", "为什么", "对比", "趋势", "analyze", "analysis"]):
        return "你希望分析的指标是什么？时间范围、对比维度（产线/班次/机台）分别是什么？"

    return "你希望我做什么：查询数据、分析原因、查看告警，还是准备/执行操作？请补充对象与时间范围。"


def _build_clarification_questions(*, text_norm: str) -> list[ClarificationQuestion]:
    question = _build_clarification_question(text_norm)
    return [
        ClarificationQuestion(
            questionId=f"q_{uuid.uuid4().hex}",
            question=question,
        )
    ]


def _infer_risk_level(*, intent: IntentType, needs_clarification: bool) -> RiskLevel:
    if needs_clarification:
        return RiskLevel.MEDIUM
    if intent == IntentType.ACTION_EXECUTE:
        return RiskLevel.HIGH
    if intent == IntentType.ACTION_PREPARE:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def identify_intent(*, ctx: RequestContext, text: str) -> IntentResult:
    text_norm = _normalize_text(text)

    scores = _score_intents(text_norm)
    intent, confidence, margin = _choose_intent(scores)

    needs_clarification = False
    reason_codes: list[str] = []

    if not text_norm:
        needs_clarification = True
        reason_codes.append("EMPTY_TEXT")
    if confidence < 0.55:
        needs_clarification = True
        reason_codes.append("LOW_CONFIDENCE")
    if margin <= 0.1 and max(scores.values()) > 0:
        needs_clarification = True
        reason_codes.append("LOW_MARGIN")

    if max(scores.values()) > 0:
        reason_codes.append("KEYWORD_MATCH")

    clarification_questions = (
        _build_clarification_questions(text_norm=text_norm) if needs_clarification else []
    )

    selected_intent = intent if not needs_clarification else _CLARIFY_INTENT
    has_write_intent = needs_clarification or selected_intent in {
        IntentType.ACTION_PREPARE,
        IntentType.ACTION_EXECUTE,
    }
    risk_level = _infer_risk_level(intent=selected_intent, needs_clarification=needs_clarification)

    result = IntentResult(
        intent=selected_intent,
        confidence=confidence,
        needs_clarification=needs_clarification,
        clarification_questions=clarification_questions,
        reason_codes=reason_codes,
        reason_summary=None,
        has_write_intent=has_write_intent,
        risk_level=risk_level,
    )

    logger.info(
        "intent_identified",
        requestId=ctx.request_id,
        tenantId=ctx.tenant_id,
        projectId=ctx.project_id,
        sessionId=ctx.session_id,
        intent=result.intent.value,
        confidence=result.confidence,
        needsClarification=result.needs_clarification,
        hasWriteIntent=result.has_write_intent,
        riskLevel=result.risk_level.value,
    )

    action_summary: dict[str, Any] = {
        "intent": result.intent.value,
        "confidence": result.confidence,
        "needsClarification": result.needs_clarification,
        "clarificationQuestions": [q.model_dump(by_alias=True) for q in result.clarification_questions],
        "reasonCodes": list(result.reason_codes),
        "hasWriteIntent": result.has_write_intent,
        "riskLevel": result.risk_level.value,
    }

    write_audit_event(
        ctx=ctx,
        event_type="intent.classified",
        resource="intent",
        action_summary=action_summary,
        result_status="success",
        error_code=None,
        evidence_refs=None,
    )

    return result
