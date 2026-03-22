from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.guardrail.policy import GuardrailPolicy, GuardrailRule, load_guardrail_policy
from gangqing.schemas.guardrail import GuardrailAction, GuardrailDecision, GuardrailHit, GuardrailHitLocation
from gangqing_db.evidence import Evidence
from gangqing_db.evidence import EvidenceTimeRange


_COMPILED_RULES: dict[tuple[str, ...], tuple[re.Pattern[str], ...]] = {}
_CACHED_GUARDRAIL_POLICY: GuardrailPolicy | None = None


def get_guardrail_policy_cached() -> GuardrailPolicy:
    global _CACHED_GUARDRAIL_POLICY
    if _CACHED_GUARDRAIL_POLICY is None:
        _CACHED_GUARDRAIL_POLICY = load_guardrail_policy()
    return _CACHED_GUARDRAIL_POLICY


@dataclass(frozen=True)
class InputDigest:
    sha256: str
    length: int


def build_input_digest(text: str) -> InputDigest:
    raw = (text or "")
    normalized = raw.strip().replace("\r\n", "\n")
    h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return InputDigest(sha256=h, length=len(normalized))


def _compile_patterns(rule: GuardrailRule) -> list[re.Pattern[str]]:
    key = tuple(rule.patterns or ())
    cached = _COMPILED_RULES.get(key)
    if cached is not None:
        return list(cached)

    compiled: list[re.Pattern[str]] = []
    for p in rule.patterns or ():
        pattern = (p or "").strip()
        if not pattern:
            continue
        compiled.append(re.compile(pattern))

    _COMPILED_RULES[key] = tuple(compiled)
    return compiled


def evaluate_text(
    *,
    policy: GuardrailPolicy | None = None,
    hit_location: GuardrailHitLocation,
    text: str,
) -> GuardrailDecision:
    effective_policy = policy or get_guardrail_policy_cached()
    raw = text or ""

    hits: list[GuardrailHit] = []
    strongest_action: GuardrailAction = GuardrailAction.ALLOW
    strongest_error_code: str | None = None

    for rule in effective_policy.rules:
        if rule.hit_location != hit_location:
            continue

        patterns = _compile_patterns(rule)
        matched = False
        for pat in patterns:
            if pat.search(raw):
                matched = True
                break
        if not matched:
            continue

        reason_summary = _default_reason_summary(rule=rule)
        hits.append(
            GuardrailHit(
                ruleId=rule.rule_id,
                category=rule.category,
                hitLocation=rule.hit_location,
                reasonSummary=reason_summary,
            )
        )

        action, error_code = _map_action(rule.action)
        if _is_stronger_action(action, strongest_action):
            strongest_action = action
            strongest_error_code = error_code

    if strongest_action == GuardrailAction.ALLOW:
        return GuardrailDecision(action=GuardrailAction.ALLOW, errorCode=None, retryable=False, hits=[])

    return GuardrailDecision(
        action=strongest_action,
        errorCode=strongest_error_code,
        retryable=False,
        hits=hits,
    )


def _default_reason_summary(*, rule: GuardrailRule) -> str:
    if rule.category == "prompt_injection":
        return "Prompt injection pattern detected"
    if rule.category == "output_safety":
        return "Unsafe output pattern detected"
    return "Guardrail rule matched"


def _map_action(action: GuardrailAction) -> tuple[GuardrailAction, str | None]:
    if action == GuardrailAction.BLOCK_FORBIDDEN:
        return GuardrailAction.BLOCK_FORBIDDEN, ErrorCode.FORBIDDEN.value
    if action == GuardrailAction.BLOCK_GUARDRAIL:
        return GuardrailAction.BLOCK_GUARDRAIL, ErrorCode.GUARDRAIL_BLOCKED.value
    if action == GuardrailAction.WARN_DEGRADE:
        return GuardrailAction.WARN_DEGRADE, None
    return GuardrailAction.ALLOW, None


def _is_stronger_action(a: GuardrailAction, b: GuardrailAction) -> bool:
    priority: dict[GuardrailAction, int] = {
        GuardrailAction.ALLOW: 0,
        GuardrailAction.WARN_DEGRADE: 1,
        GuardrailAction.BLOCK_FORBIDDEN: 2,
        GuardrailAction.BLOCK_GUARDRAIL: 3,
    }
    return priority.get(a, 0) > priority.get(b, 0)


def decision_to_app_error(*, ctx: RequestContext, stage: str, decision: GuardrailDecision) -> AppError:
    if decision.action == GuardrailAction.BLOCK_FORBIDDEN:
        return AppError(
            ErrorCode.FORBIDDEN,
            "Forbidden",
            request_id=ctx.request_id,
            details=_build_error_details(stage=stage, decision=decision),
            retryable=False,
        )

    return AppError(
        ErrorCode.GUARDRAIL_BLOCKED,
        "Guardrail blocked unsafe request",
        request_id=ctx.request_id,
        details=_build_error_details(stage=stage, decision=decision),
        retryable=False,
    )


def _build_error_details(*, stage: str, decision: GuardrailDecision) -> dict[str, Any]:
    hits = [h.model_dump(by_alias=True) for h in decision.hits]
    first_hit = decision.hits[0] if decision.hits else None
    return {
        "stage": stage,
        "ruleId": getattr(first_hit, "rule_id", None) if first_hit is not None else None,
        "reasonSummary": getattr(first_hit, "reason_summary", None) if first_hit is not None else None,
        "hitLocation": getattr(first_hit, "hit_location", None).value if first_hit is not None else None,
        "hits": hits,
    }


def write_guardrail_audit(
    *,
    ctx: RequestContext,
    stage: str,
    decision: GuardrailDecision,
    input_digest: InputDigest | None,
    result_status: str,
    evidence_refs: list[str] | None = None,
    extra_action_summary: dict[str, Any] | None = None,
) -> None:
    hits = [h.model_dump(by_alias=True) for h in decision.hits]
    now = datetime.now(timezone.utc)
    action_summary: dict[str, Any] = {
        "stage": stage,
        "decisionAction": decision.action.value,
        "riskLevel": _risk_level(decision.action),
        "timestamp": now.isoformat(),
        "policy": _safe_policy_key(),
        "policyVersion": _safe_policy_key(),
        "hits": hits,
    }
    if input_digest is not None:
        action_summary["inputDigest"] = {"sha256": input_digest.sha256, "length": input_digest.length}

    if extra_action_summary:
        for k, v in extra_action_summary.items():
            if k not in action_summary:
                action_summary[k] = v

    write_audit_event(
        ctx=ctx,
        event_type=AuditEventType.GUARDRAIL_HIT.value,
        resource="guardrail",
        action_summary=action_summary,
        result_status=result_status,
        error_code=decision.error_code,
        evidence_refs=evidence_refs,
    )


def _safe_policy_key() -> str:
    try:
        p = get_guardrail_policy_cached()
        return f"{p.policy_id}@{p.version}"
    except Exception:
        return "unknown"


def _risk_level(action: GuardrailAction) -> str:
    if action in {GuardrailAction.BLOCK_FORBIDDEN, GuardrailAction.BLOCK_GUARDRAIL}:
        return "high"
    if action == GuardrailAction.WARN_DEGRADE:
        return "medium"
    return "low"


def build_text_preview_digest(value: Any, *, max_chars: int = 8000) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        raw = str(value)
    raw = raw[:max_chars]
    return build_input_digest(raw).sha256


def build_guardrail_evidence(
    *,
    ctx: RequestContext,
    stage: str,
    decision: GuardrailDecision,
) -> Evidence:
    now = datetime.now(timezone.utc)
    first_hit = decision.hits[0] if decision.hits else None

    rule_id = getattr(first_hit, "rule_id", None) if first_hit is not None else None
    category = getattr(first_hit, "category", None) if first_hit is not None else None
    reason_summary = getattr(first_hit, "reason_summary", None) if first_hit is not None else None
    hit_location = getattr(first_hit, "hit_location", None).value if first_hit is not None else None

    evidence_id = f"ev_guardrail_{uuid.uuid4().hex}"
    locator: dict[str, Any] = {
        "ruleId": rule_id,
        "category": category,
        "reasonSummary": reason_summary,
        "hitLocation": hit_location,
        "timestamp": now.isoformat(),
        "requestId": ctx.request_id,
        "sessionId": ctx.session_id,
        "stage": stage,
        "decisionAction": decision.action.value,
    }

    # EvidenceTimeRange requires end > start.
    time_range = EvidenceTimeRange(start=now, end=now + timedelta(microseconds=1))
    return Evidence(
        evidenceId=evidence_id,
        sourceSystem="Detector",
        sourceLocator=locator,
        timeRange=time_range,
        toolCallId=None,
        lineageVersion=None,
        dataQualityScore=None,
        confidence="High",
        validation="not_verifiable",
        redactions=None,
    )
