from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from gangqing.common.settings import load_settings


class MaskingPolicy(BaseModel):
    policy_id: str = Field(min_length=1, alias="policyId")
    version: str = Field(min_length=1)
    default_action: str = Field(default="mask", pattern=r"^(mask|allow|deny)$")
    sensitive_key_fragments: tuple[str, ...] = Field(default_factory=tuple, alias="sensitiveKeyFragments")
    role_allow_fragments: dict[str, tuple[str, ...]] = Field(default_factory=dict, alias="roleAllowFragments")

    domains: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    role_allow_domains: dict[str, tuple[str, ...]] = Field(default_factory=dict, alias="roleAllowDomains")

    field_path_rules: dict[str, str] = Field(default_factory=dict, alias="fieldPathRules")
    role_allow_field_paths: dict[str, tuple[str, ...]] = Field(
        default_factory=dict,
        alias="roleAllowFieldPaths",
    )

    model_config = {"populate_by_name": True}


_DEFAULT_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "unit_cost",
    "total_cost",
    "cost",
    "profit",
    "price",
    "salary",
    "supplier_price",
    "recipe",
    "formula",
)


_DEFAULT_DOMAINS: dict[str, tuple[str, ...]] = {
    "Finance": (
        "unit_cost",
        "total_cost",
        "cost",
        "profit",
        "price",
        "salary",
        "supplier_price",
    ),
    "Recipe": (
        "recipe",
        "formula",
    ),
    "Process": tuple(),
    "PII": tuple(),
}


def build_default_masking_policy() -> MaskingPolicy:
    settings = load_settings()
    return MaskingPolicy(
        policyId="masking_default",
        version="v1",
        default_action=settings.masking_default_action,
        sensitiveKeyFragments=_DEFAULT_SENSITIVE_KEY_FRAGMENTS,
        domains=_DEFAULT_DOMAINS,
        roleAllowFragments={
            "finance": (
                "unit_cost",
                "total_cost",
                "cost",
                "profit",
                "price",
                "supplier_price",
            ),
        },
        roleAllowDomains={
            "finance": ("Finance",),
        },
    )


def load_masking_policy() -> MaskingPolicy:
    settings = load_settings()
    raw = (settings.masking_policy_json or "").strip()
    if not raw:
        # Backward compatible env var support.
        raw = (os.environ.get("GANGQING_MASKING_POLICY_JSON") or "").strip()
    if not raw:
        if settings.masking_policy_required:
            raise ValueError("Missing masking policy")
        return build_default_masking_policy()

    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError("Invalid masking policy JSON") from e

    try:
        return MaskingPolicy.model_validate(obj)
    except Exception as e:
        raise ValueError("Invalid masking policy schema") from e


@dataclass(frozen=True)
class _CompiledPolicy:
    policy_key: str
    default_action: str
    sensitive_fragments: frozenset[str]
    allow_fragments: frozenset[str]
    domain_fragments: dict[str, frozenset[str]]
    allow_domains: frozenset[str]
    field_path_rules: dict[str, str]
    allow_field_paths: frozenset[str]


def _normalize_action(action: str) -> str:
    value = (action or "").strip().lower()
    if value not in {"mask", "allow", "deny"}:
        return "mask"
    return value


@lru_cache(maxsize=256)
def _compile_policy_cached(policy_id: str, version: str, role_key: str, policy_json: str) -> _CompiledPolicy:
    policy = MaskingPolicy.model_validate(json.loads(policy_json))
    allow_fragments = frozenset(
        (f or "").strip().lower() for f in policy.role_allow_fragments.get(role_key, ()) if (f or "").strip()
    )
    sensitive_fragments = frozenset((f or "").strip().lower() for f in policy.sensitive_key_fragments if (f or "").strip())

    domain_fragments: dict[str, frozenset[str]] = {}
    for domain_name, frags in (policy.domains or {}).items():
        domain_fragments[str(domain_name)] = frozenset(
            (f or "").strip().lower() for f in (frags or ()) if (f or "").strip()
        )

    allow_domains = frozenset(
        str(d) for d in policy.role_allow_domains.get(role_key, ()) if str(d).strip()
    )
    allow_field_paths = frozenset(
        str(p) for p in policy.role_allow_field_paths.get(role_key, ()) if str(p).strip()
    )

    field_path_rules = {str(k): _normalize_action(str(v)) for k, v in (policy.field_path_rules or {}).items()}
    return _CompiledPolicy(
        policy_key=f"{policy_id}@{version}",
        default_action=_normalize_action(policy.default_action),
        sensitive_fragments=sensitive_fragments,
        allow_fragments=allow_fragments,
        domain_fragments=domain_fragments,
        allow_domains=allow_domains,
        field_path_rules=field_path_rules,
        allow_field_paths=allow_field_paths,
    )


def _compile_policy(policy: MaskingPolicy, *, role_key: str) -> _CompiledPolicy:
    policy_json = json.dumps(policy.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True)
    return _compile_policy_cached(policy.policy_id, policy.version, role_key, policy_json)


def apply_role_based_masking(
    value: Any,
    *,
    role: str | None,
    policy: MaskingPolicy | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    effective_policy = policy or build_default_masking_policy()
    role_key = (role or "").strip().lower()
    compiled = _compile_policy(effective_policy, role_key=role_key)

    masked_keys: set[str] = set()

    def _mask(v: Any, *, path: str) -> Any:
        if v is None:
            return None
        if isinstance(v, Mapping):
            out: dict[str, Any] = {}
            for k, inner in v.items():
                key_str = str(k)
                key_lower = key_str.lower()
                child_path = f"{path}.{key_str}" if path else key_str

                rule_action = compiled.field_path_rules.get(child_path)
                if rule_action and child_path not in compiled.allow_field_paths:
                    if rule_action == "deny":
                        out[key_str] = None
                    elif rule_action == "allow":
                        out[key_str] = _mask(inner, path=child_path)
                    else:
                        out[key_str] = "[MASKED]"
                    masked_keys.add(key_str)

                    continue

                matched = [f for f in compiled.sensitive_fragments if f in key_lower]
                if matched:
                    is_allowed_by_fragment = any(f in key_lower for f in compiled.allow_fragments)
                    is_allowed_by_domain = False
                    if compiled.allow_domains and compiled.domain_fragments:
                        for domain_name, frags in compiled.domain_fragments.items():
                            if domain_name not in compiled.allow_domains:
                                continue
                            if any(f in key_lower for f in frags):
                                is_allowed_by_domain = True
                                break

                    if not is_allowed_by_fragment and not is_allowed_by_domain:
                        if compiled.default_action == "deny":
                            out[key_str] = None
                        elif compiled.default_action == "allow":
                            out[key_str] = _mask(inner, path=child_path)
                        else:
                            out[key_str] = "[MASKED]"
                        masked_keys.add(key_str)
                        continue

                out[key_str] = _mask(inner, path=child_path)
            return out
        if isinstance(v, (list, tuple)):
            return [_mask(i, path=path) for i in v]
        if isinstance(v, (bytes, bytearray)):
            return "[MASKED]"
        return v

    masked_value = _mask(value, path="")
    if not masked_keys:
        return masked_value, None

    return masked_value, {
        "policyId": effective_policy.policy_id,
        "version": effective_policy.version,
        "maskedKeys": sorted(masked_keys),
    }
