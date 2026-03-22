from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolAccessMode(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"


class ToolGovernance(BaseModel):
    access_mode: ToolAccessMode = Field(alias="accessMode")
    requires_approval: bool = Field(alias="requiresApproval")

    model_config = {"populate_by_name": True}


class ToolExecutionPolicy(BaseModel):
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")
    max_retries: int | None = Field(default=None, alias="maxRetries")

    model_config = {"populate_by_name": True}


class ToolRbacPolicy(BaseModel):
    required_capability: str | None = Field(default=None, alias="requiredCapability")

    model_config = {"populate_by_name": True}


class ToolRedactionPolicyRef(BaseModel):
    policy_id: str | None = Field(default=None, alias="policyId")

    model_config = {"populate_by_name": True}


class ToolContractRefs(BaseModel):
    params_model: str = Field(alias="paramsModel")
    result_model: str | None = Field(default=None, alias="resultModel")
    output_contract_source: str | None = Field(default=None, alias="outputContractSource")

    model_config = {"populate_by_name": True}


class ToolMetadata(BaseModel):
    tool_name: str = Field(alias="toolName")
    version: str | None = None

    enabled: bool

    governance: ToolGovernance
    rbac: ToolRbacPolicy
    execution: ToolExecutionPolicy
    redaction: ToolRedactionPolicyRef
    contracts: ToolContractRefs

    data_domains: list[str] = Field(default_factory=list, alias="dataDomains")
    tags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ToolSpecForRouting(BaseModel):
    name: str
    required_capability: str | None = Field(default=None, alias="requiredCapability")

    model_config = {"populate_by_name": True}


def build_args_summary_for_audit(*, raw_params: dict[str, Any]) -> dict[str, Any]:
    return {"args": raw_params}
