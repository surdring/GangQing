from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import TypeVar

from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.settings import load_settings
from gangqing.tools.metadata import (
    ToolAccessMode,
    ToolContractRefs,
    ToolExecutionPolicy,
    ToolGovernance,
    ToolMetadata,
    ToolRbacPolicy,
    ToolRedactionPolicyRef,
    ToolSpecForRouting,
)


def _parse_csv_list(value: str) -> list[str]:
    """解析逗号分隔的工具名列表。

    参数：
    - value: 逗号分隔字符串

    返回：
    - 去掉空白/空项后的工具名列表
    """
    items: list[str] = []
    for raw in (value or "").split(","):
        s = raw.strip()
        if s:
            items.append(s)
    return items


@dataclass(frozen=True)
class ToolRegistryConfig:
    enabled: bool
    enabled_list: list[str]
    disabled_list: list[str]


def load_tool_registry_config() -> ToolRegistryConfig:
    """从 settings/env 加载工具注册表配置（单一事实源）。

    返回：
    - ToolRegistryConfig: 包含 enabled 开关、enabled_list 白名单、disabled_list 黑名单。

    异常：
    - AppError(CONTRACT_VIOLATION):
      - enabled_list 与 disabled_list 冲突
      - 工具名为空字符串
    """

    settings = load_settings()
    enabled = bool(getattr(settings, "tool_registry_enabled", True))
    enabled_list = _parse_csv_list(getattr(settings, "tool_enabled_list", "") or "")
    disabled_list = _parse_csv_list(getattr(settings, "tool_disabled_list", "") or "")

    enabled_names = set(enabled_list)
    disabled_names = set(disabled_list)
    conflicts = sorted(enabled_names.intersection(disabled_names))
    if conflicts:
        raise AppError(
            ErrorCode.CONTRACT_VIOLATION,
            "Invalid tool registry config",
            request_id="unknown",
            details={"reason": "enabled_disabled_conflict", "toolNames": conflicts},
            retryable=False,
        )

    for name in enabled_list + disabled_list:
        if not name:
            raise AppError(
                ErrorCode.CONTRACT_VIOLATION,
                "Invalid tool registry config",
                request_id="unknown",
                details={"reason": "empty_tool_name"},
                retryable=False,
            )

    return ToolRegistryConfig(
        enabled=enabled,
        enabled_list=enabled_list,
        disabled_list=disabled_list,
    )


class ToolRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ToolMetadata] = {}

    def register(self, meta: ToolMetadata) -> None:
        """注册一个工具元数据条目。

        参数：
        - meta: ToolMetadata（必须包含 toolName/version 等）

        异常：
        - AppError(CONTRACT_VIOLATION):
          - version 缺失
          - 相同 toolName 的 version 冲突
        """
        if not (meta.version or "").strip():
            raise AppError(
                ErrorCode.CONTRACT_VIOLATION,
                "Invalid tool metadata",
                request_id="unknown",
                details={"reason": "missing_version", "toolName": meta.tool_name},
                retryable=False,
            )

        existing = self._items.get(meta.tool_name)
        if existing is not None and str(existing.version) != str(meta.version):
            raise AppError(
                ErrorCode.CONTRACT_VIOLATION,
                "Tool version conflict",
                request_id="unknown",
                details={
                    "reason": "version_conflict",
                    "toolName": meta.tool_name,
                    "existingVersion": existing.version,
                    "newVersion": meta.version,
                },
                retryable=False,
            )
        self._items[meta.tool_name] = meta

    def list_all(self) -> list[ToolMetadata]:
        """列出所有已注册工具（不应用 enable/disable 过滤）。"""
        return [self._items[k] for k in sorted(self._items.keys())]

    def list_enabled(self) -> list[ToolMetadata]:
        """列出当前可执行的工具元数据列表。

        规则：
        - registry 开关关闭 => 空列表
        - disabled_list 优先生效
        - enabled_list 非空时 => 仅允许白名单
        - meta.enabled=false 的工具永不返回
        """
        cfg = load_tool_registry_config()
        if not cfg.enabled:
            return []

        enabled_names = set(cfg.enabled_list)
        disabled_names = set(cfg.disabled_list)

        metas: list[ToolMetadata] = []
        for meta in self.list_all():
            if meta.tool_name in disabled_names:
                continue
            if enabled_names and meta.tool_name not in enabled_names:
                continue
            if not meta.enabled:
                continue
            metas.append(meta)

        return metas

    def build_tool_specs_for_routing(self) -> list[ToolSpecForRouting]:
        specs: list[ToolSpecForRouting] = []
        for meta in self.list_enabled():
            if meta.governance.access_mode != ToolAccessMode.READ_ONLY:
                continue
            specs.append(
                ToolSpecForRouting(
                    name=meta.tool_name,
                    required_capability=meta.rbac.required_capability,
                )
            )
        return specs


def build_default_registry() -> ToolRegistry:
    """Build the default in-process tool registry.

    At L1 phase we only register read-only tools for execution.
    Write tools may be registered later for capability display, but they must not
    be executable via the chat orchestration path.
    """

    registry = ToolRegistry()

    _import_default_tools_for_registration()
    for meta in list_registered_tool_metadata():
        registry.register(meta)

    return registry


_T = TypeVar("_T")
_AUTO_TOOL_METADATA: list[ToolMetadata] = []


def tool_metadata(meta: ToolMetadata) -> Callable[[_T], _T]:
    """装饰器：声明式注册工具元数据。

    用法：
    - 在工具类定义上方使用 `@tool_metadata(...)`。
    - registry 构建阶段会导入工具模块触发装饰器执行，并汇总全部 ToolMetadata。
    """
    def _decorator(obj: _T) -> _T:
        _AUTO_TOOL_METADATA.append(meta)
        return obj

    return _decorator


def list_registered_tool_metadata() -> list[ToolMetadata]:
    """返回当前进程内通过装饰器注册的所有 ToolMetadata。"""
    return list(_AUTO_TOOL_METADATA)


def _import_default_tools_for_registration() -> None:
    """导入默认工具模块以触发装饰器注册。

    说明：
    - 该函数不返回值；其副作用是将工具元数据加入注册表。
    """
    from gangqing.tools import postgres_readonly  # noqa: F401
