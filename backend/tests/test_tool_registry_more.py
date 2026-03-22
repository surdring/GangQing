from __future__ import annotations

import os

import pytest

from gangqing.common.errors import AppError, ErrorCode
from gangqing.tools.metadata import ToolAccessMode, ToolGovernance, ToolMetadata, ToolRbacPolicy, ToolExecutionPolicy, ToolRedactionPolicyRef, ToolContractRefs
from gangqing.tools.registry import ToolRegistry, load_tool_registry_config


def test_registry_config_conflict_enabled_and_disabled_list_raises() -> None:
    os.environ["GANGQING_TOOL_REGISTRY_ENABLED"] = "true"
    os.environ["GANGQING_TOOL_ENABLED_LIST"] = "postgres_readonly_query"
    os.environ["GANGQING_TOOL_DISABLED_LIST"] = "postgres_readonly_query"

    with pytest.raises(AppError) as e:
        load_tool_registry_config()

    assert e.value.code == ErrorCode.CONTRACT_VIOLATION


def test_registry_register_requires_version() -> None:
    registry = ToolRegistry()
    meta = ToolMetadata(
        toolName="t1",
        version=None,
        enabled=True,
        governance=ToolGovernance(accessMode=ToolAccessMode.READ_ONLY, requiresApproval=False),
        rbac=ToolRbacPolicy(requiredCapability=None),
        execution=ToolExecutionPolicy(timeoutSeconds=None, maxRetries=None),
        redaction=ToolRedactionPolicyRef(policyId="default"),
        contracts=ToolContractRefs(paramsModel="x", resultModel=None, outputContractSource=None),
        dataDomains=[],
        tags=[],
    )

    with pytest.raises(AppError) as e:
        registry.register(meta)

    assert e.value.code == ErrorCode.CONTRACT_VIOLATION


def test_registry_register_version_conflict_raises() -> None:
    registry = ToolRegistry()
    meta1 = ToolMetadata(
        toolName="t1",
        version="1",
        enabled=True,
        governance=ToolGovernance(accessMode=ToolAccessMode.READ_ONLY, requiresApproval=False),
        rbac=ToolRbacPolicy(requiredCapability=None),
        execution=ToolExecutionPolicy(timeoutSeconds=None, maxRetries=None),
        redaction=ToolRedactionPolicyRef(policyId="default"),
        contracts=ToolContractRefs(paramsModel="x", resultModel=None, outputContractSource=None),
        dataDomains=[],
        tags=[],
    )
    meta2 = meta1.model_copy(update={"version": "2"})

    registry.register(meta1)
    with pytest.raises(AppError) as e:
        registry.register(meta2)

    assert e.value.code == ErrorCode.CONTRACT_VIOLATION
