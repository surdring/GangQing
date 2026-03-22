from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from gangqing.schemas.intent import ClarificationQuestion, IntentType, RiskLevel


class RouteDecisionType(str, Enum):
    CLARIFY = "clarify"
    ALLOW = "allow"
    DRAFT = "draft"
    BLOCK = "block"


class ActionDraft(BaseModel):
    draft_id: str = Field(min_length=1, alias="draftId")
    action_type: str = Field(min_length=1, alias="actionType")
    target_resource_summary: str = Field(min_length=1, alias="targetResourceSummary")
    constraints: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = Field(alias="riskLevel")
    risk_reason_codes: list[str] = Field(default_factory=list, alias="riskReasonCodes")
    required_capabilities: list[str] = Field(default_factory=list, alias="requiredCapabilities")

    model_config = {"populate_by_name": True}


class RouteDecision(BaseModel):
    decision_type: RouteDecisionType = Field(alias="decisionType")
    selected_intent: IntentType = Field(alias="selectedIntent")
    allowed_tool_names: list[str] = Field(default_factory=list, alias="allowedToolNames")

    blocked_reason_code: str | None = Field(default=None, alias="blockedReasonCode")

    clarification: list[ClarificationQuestion] | None = None
    draft: ActionDraft | None = None

    audit_tags: dict[str, str] = Field(default_factory=dict, alias="auditTags")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_decision_shape(self) -> "RouteDecision":
        if self.decision_type == RouteDecisionType.BLOCK and not self.blocked_reason_code:
            raise ValueError("blockedReasonCode must not be empty when decisionType is block")
        if self.decision_type == RouteDecisionType.CLARIFY:
            if not self.clarification:
                raise ValueError("clarification must not be empty when decisionType is clarify")
        if self.decision_type == RouteDecisionType.DRAFT and self.draft is None:
            raise ValueError("draft must not be null when decisionType is draft")
        return self
