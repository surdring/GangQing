from __future__ import annotations

import json
import os
from functools import lru_cache

from pydantic import BaseModel
from pydantic import Field

from gangqing.common.settings import load_settings
from gangqing.schemas.guardrail import GuardrailAction
from gangqing.schemas.guardrail import GuardrailHitLocation


class GuardrailRule(BaseModel):
    rule_id: str = Field(min_length=1, alias="ruleId")
    category: str = Field(min_length=1)
    hit_location: GuardrailHitLocation = Field(alias="hitLocation")
    action: GuardrailAction
    patterns: tuple[str, ...] = Field(default_factory=tuple)

    model_config = {"populate_by_name": True}


class GuardrailPolicy(BaseModel):
    policy_id: str = Field(min_length=1, alias="policyId")
    version: str = Field(min_length=1)
    rules: tuple[GuardrailRule, ...] = Field(default_factory=tuple)

    model_config = {"populate_by_name": True}


def build_default_guardrail_policy() -> GuardrailPolicy:
    return GuardrailPolicy(
        policyId="guardrail_default",
        version="v1",
        rules=(
            GuardrailRule(
                ruleId="GUARDRAIL_INJ_DIRECT_IGNORE_RULES",
                category="prompt_injection",
                hitLocation=GuardrailHitLocation.INPUT,
                action=GuardrailAction.BLOCK_GUARDRAIL,
                patterns=(
                    r"(?i)ignore\s+(all|any|previous)\s+instructions",
                    r"(?i)disregard\s+(all|any|previous)\s+instructions",
                    r"(?i)override\s+system",
                    r"(?i)do\s+not\s+follow\s+the\s+rules",
                ),
            ),
            GuardrailRule(
                ruleId="GUARDRAIL_INJ_DIRECT_SYSTEM_PROMPT_EXFIL",
                category="prompt_injection",
                hitLocation=GuardrailHitLocation.INPUT,
                action=GuardrailAction.BLOCK_GUARDRAIL,
                patterns=(
                    r"(?i)system\s+prompt",
                    r"(?i)developer\s+message",
                    r"(?i)reveal\s+your\s+instructions",
                    r"(?i)show\s+me\s+the\s+prompt",
                    r"(?i)prompt\s+leak",
                ),
            ),
            GuardrailRule(
                ruleId="GUARDRAIL_INJ_INDIRECT_INSTRUCTION_IN_CONTEXT",
                category="prompt_injection",
                hitLocation=GuardrailHitLocation.TOOL_CONTEXT,
                action=GuardrailAction.BLOCK_GUARDRAIL,
                patterns=(
                    r"(?i)^\s*(system:|developer:)",
                    r"(?i)ignore\s+previous\s+instructions",
                    r"(?i)you\s+must\s+follow\s+these\s+steps",
                ),
            ),
            GuardrailRule(
                ruleId="GUARDRAIL_OUTPUT_SYSTEM_PROMPT_LEAK",
                category="output_safety",
                hitLocation=GuardrailHitLocation.OUTPUT,
                action=GuardrailAction.BLOCK_GUARDRAIL,
                patterns=(
                    r"(?i)\b(system prompt|developer message|internal instructions)\b",
                    r"(?i)\byou are chatgpt\b",
                    r"(?i)\bhere is the system prompt\b",
                ),
            ),
            GuardrailRule(
                ruleId="GUARDRAIL_OUTPUT_SENSITIVE_TOKEN",
                category="output_safety",
                hitLocation=GuardrailHitLocation.OUTPUT,
                action=GuardrailAction.BLOCK_GUARDRAIL,
                patterns=(
                    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)\b\s*[:=]",
                    r"(?i)\bpassword\b\s*[:=]",
                    r"(?i)\bsk-[A-Za-z0-9]{10,}\b",
                ),
            ),
        ),
    )


@lru_cache(maxsize=1)
def load_guardrail_policy() -> GuardrailPolicy:
    settings = load_settings()
    raw = (getattr(settings, "guardrail_policy_json", "") or "").strip()
    if not raw:
        raw = (os.environ.get("GANGQING_GUARDRAIL_POLICY_JSON") or "").strip()

    if not raw:
        if bool(getattr(settings, "guardrail_policy_required", False)):
            raise ValueError("Missing guardrail policy")
        return build_default_guardrail_policy()

    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError("Invalid guardrail policy JSON") from e

    try:
        return GuardrailPolicy.model_validate(obj)
    except Exception as e:
        raise ValueError("Invalid guardrail policy schema") from e
