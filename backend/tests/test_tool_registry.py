from __future__ import annotations

import os

from gangqing.tools.registry import build_default_registry


def test_tool_registry_enabled_filters_by_disabled_list() -> None:
    os.environ["GANGQING_TOOL_REGISTRY_ENABLED"] = "true"
    os.environ["GANGQING_TOOL_ENABLED_LIST"] = ""
    os.environ["GANGQING_TOOL_DISABLED_LIST"] = "postgres_readonly_query"

    registry = build_default_registry()
    enabled = registry.list_enabled()
    assert [m.tool_name for m in enabled] == []


def test_tool_registry_enabled_filters_by_enabled_list() -> None:
    os.environ["GANGQING_TOOL_REGISTRY_ENABLED"] = "true"
    os.environ["GANGQING_TOOL_ENABLED_LIST"] = "postgres_readonly_query"
    os.environ["GANGQING_TOOL_DISABLED_LIST"] = ""

    registry = build_default_registry()
    enabled = registry.list_enabled()
    assert [m.tool_name for m in enabled] == ["postgres_readonly_query"]


def test_tool_registry_disabled_returns_empty() -> None:
    os.environ["GANGQING_TOOL_REGISTRY_ENABLED"] = "false"
    os.environ["GANGQING_TOOL_ENABLED_LIST"] = ""
    os.environ["GANGQING_TOOL_DISABLED_LIST"] = ""

    registry = build_default_registry()
    enabled = registry.list_enabled()
    assert enabled == []
