from __future__ import annotations

from enum import Enum

from pydantic import BaseModel
from pydantic import Field


class GuardrailHitLocation(str, Enum):
    INPUT = "input"
    TOOL_CONTEXT = "tool_context"
    OUTPUT = "output"


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    WARN_DEGRADE = "warn_degrade"
    BLOCK_FORBIDDEN = "block_forbidden"
    BLOCK_GUARDRAIL = "block_guardrail"


class GuardrailHit(BaseModel):
    rule_id: str = Field(min_length=1, alias="ruleId")
    category: str = Field(min_length=1)
    hit_location: GuardrailHitLocation = Field(alias="hitLocation")
    reason_summary: str = Field(min_length=1, alias="reasonSummary")
    risk_level: str | None = Field(default=None, alias="riskLevel")
    policy_version: str | None = Field(default=None, alias="policyVersion")
    evidence_id: str | None = Field(default=None, alias="evidenceId")

    model_config = {"populate_by_name": True}


class GuardrailDecision(BaseModel):
    action: GuardrailAction
    error_code: str | None = Field(default=None, alias="errorCode")
    retryable: bool = False
    hits: list[GuardrailHit] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
