from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class IntentType(str, Enum):
    QUERY = "QUERY"
    ANALYZE = "ANALYZE"
    ALERT = "ALERT"
    ACTION_PREPARE = "ACTION_PREPARE"
    ACTION_EXECUTE = "ACTION_EXECUTE"


class ClarificationQuestion(BaseModel):
    question_id: str = Field(min_length=1, alias="questionId")
    question: str = Field(min_length=1)

    model_config = {"populate_by_name": True}


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IntentResult(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)

    needs_clarification: bool = Field(alias="needsClarification")
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list, alias="clarificationQuestions"
    )

    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    reason_summary: str | None = Field(default=None, alias="reasonSummary")

    has_write_intent: bool = Field(alias="hasWriteIntent")
    risk_level: RiskLevel = Field(alias="riskLevel")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_clarification_questions(self) -> "IntentResult":
        if self.needs_clarification and not self.clarification_questions:
            raise ValueError("clarificationQuestions must not be empty when needsClarification is true")
        return self
