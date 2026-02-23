from __future__ import annotations

import os

import pytest

from gangqing.common.masking import apply_role_based_masking, build_default_masking_policy
from gangqing.common.masking import load_masking_policy
from gangqing.common.masking import MaskingPolicy
from gangqing.common.masking import _compile_policy_cached


def test_masking_default_masks_sensitive_fields_for_non_finance_role() -> None:
    policy = build_default_masking_policy()
    masked, meta = apply_role_based_masking(
        {
            "unit_cost": 12.34,
            "nested": {"total_cost": 99.9, "safe": "ok"},
            "safe": "v",
        },
        role="plant_manager",
        policy=policy,
    )

    assert masked["unit_cost"] == "[MASKED]"
    assert masked["nested"]["total_cost"] == "[MASKED]"
    assert masked["nested"]["safe"] == "ok"
    assert masked["safe"] == "v"
    assert meta is not None
    assert meta["policyId"] == policy.policy_id
    assert meta["version"] == policy.version
    assert "unit_cost" in meta["maskedKeys"]


def test_masking_finance_allows_finance_fields() -> None:
    policy = build_default_masking_policy()
    masked, meta = apply_role_based_masking(
        {
            "unit_cost": 12.34,
            "total_cost": 99.9,
            "safe": "v",
        },
        role="finance",
        policy=policy,
    )

    assert masked["unit_cost"] == 12.34
    assert masked["total_cost"] == 99.9
    assert masked["safe"] == "v"
    assert meta is None


def test_masking_handles_none_and_collections_and_bytes() -> None:
    policy = build_default_masking_policy()
    masked, meta = apply_role_based_masking(
        {
            "unit_cost": None,
            "items": [
                {"total_cost": 1.0},
                {"safe": "ok"},
            ],
            "blob": b"secret",
        },
        role="plant_manager",
        policy=policy,
    )

    assert masked["unit_cost"] == "[MASKED]"
    assert masked["items"][0]["total_cost"] == "[MASKED]"
    assert masked["items"][1]["safe"] == "ok"
    assert masked["blob"] == "[MASKED]"
    assert meta is not None
    assert "unit_cost" in meta["maskedKeys"]


def test_load_masking_policy_required_missing_raises() -> None:
    os.environ.pop("GANGQING_MASKING_POLICY_JSON", None)
    os.environ["GANGQING_MASKING_POLICY_REQUIRED"] = "true"
    os.environ["GANGQING_MASKING_POLICY_JSON"] = ""

    with pytest.raises(ValueError) as exc_info:
        load_masking_policy()
    assert "Missing masking policy" in str(exc_info.value)


def test_load_masking_policy_invalid_json_raises() -> None:
    os.environ["GANGQING_MASKING_POLICY_REQUIRED"] = "true"
    os.environ["GANGQING_MASKING_POLICY_JSON"] = "{bad json"

    with pytest.raises(ValueError) as exc_info:
        load_masking_policy()
    assert "Invalid masking policy JSON" in str(exc_info.value)


def test_masking_field_path_rules_override() -> None:
    policy = MaskingPolicy(
        policyId="p1",
        version="v1",
        default_action="mask",
        sensitiveKeyFragments=("cost",),
        fieldPathRules={"a.b": "deny"},
        roleAllowFieldPaths={"finance": ("a.b",)},
    )

    masked_pm, _ = apply_role_based_masking({"a": {"b": 1, "cost": 2}}, role="plant_manager", policy=policy)
    assert masked_pm["a"]["b"] is None

    masked_fin, _ = apply_role_based_masking({"a": {"b": 1, "cost": 2}}, role="finance", policy=policy)
    assert masked_fin["a"]["b"] == 1


def test_masking_domain_allow_allows_finance_domain() -> None:
    policy = MaskingPolicy(
        policyId="p2",
        version="v1",
        default_action="mask",
        sensitiveKeyFragments=("unit_cost",),
        domains={"Finance": ("unit_cost",)},
        roleAllowDomains={"finance": ("Finance",)},
    )

    masked_pm, _ = apply_role_based_masking({"unit_cost": 10}, role="plant_manager", policy=policy)
    assert masked_pm["unit_cost"] == "[MASKED]"

    masked_fin, meta_fin = apply_role_based_masking({"unit_cost": 10}, role="finance", policy=policy)
    assert masked_fin["unit_cost"] == 10
    assert meta_fin is None


def test_masking_compile_cache_hits() -> None:
    _compile_policy_cached.cache_clear()
    policy = build_default_masking_policy()
    raw = policy.model_dump(by_alias=True)
    policy_json = __import__("json").dumps(raw, ensure_ascii=False, sort_keys=True)

    _compile_policy_cached(policy.policy_id, policy.version, "plant_manager", policy_json)
    info1 = _compile_policy_cached.cache_info()
    _compile_policy_cached(policy.policy_id, policy.version, "plant_manager", policy_json)
    info2 = _compile_policy_cached.cache_info()

    assert info2.hits == info1.hits + 1
