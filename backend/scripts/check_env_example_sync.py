#!/usr/bin/env python3
"""Configuration consistency checker - validates .env.example sync with code.

This script checks that all configuration fields defined in the Pydantic model
are present in .env.example, and vice versa.

Usage:
    cd /home/surdring/workspace/GangQing
    source .venv/bin/activate
    python backend/scripts/check_env_example_sync.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _iter_text_files(project_root: Path) -> list[Path]:
    excluded_dir_names = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache"}
    included_suffixes = {".py", ".md", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".sh"}

    paths: list[Path] = []
    for path in project_root.rglob("*"):
        if any(part in excluded_dir_names for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix not in included_suffixes:
            continue
        paths.append(path)
    return paths


def _build_reference_index(project_root: Path) -> str:
    chunks: list[str] = []
    for path in _iter_text_files(project_root):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n".join(chunks)


def extract_config_fields_from_model(model_path: Path) -> set[str]:
    """Extract all configuration field names from the Pydantic model."""
    content = model_path.read_text(encoding="utf-8")

    # Pattern to match Field declarations: field_name: type = Field(...)
    pattern = r"^\s+(\w+):\s*\w+\s*=\s*Field"

    fields = set()
    for line in content.split("\n"):
        match = re.match(pattern, line)
        if match:
            field_name = match.group(1)
            # Convert snake_case to UPPER_SNAKE_CASE with GANGQING_ prefix
            env_var = "GANGQING_" + field_name.upper()
            fields.add(env_var)

    return fields


def extract_config_fields_from_env_example(env_path: Path) -> set[str]:
    """Extract all configuration keys from .env.example."""
    content = env_path.read_text(encoding="utf-8")

    fields = set()
    for line in content.split("\n"):
        line = line.strip()
        # Match lines like: GANGQING_XXX=value or GANGQING_XXX= (empty value)
        if line and not line.startswith("#"):
            if "=" in line:
                key = line.split("=", 1)[0].strip()
                if key.startswith("GANGQING_"):
                    fields.add(key)

    return fields


def main() -> int:
    """Main entry point."""
    project_root = Path(__file__).resolve().parents[2]

    model_path = project_root / "backend" / "gangqing" / "config.py"
    env_path = project_root / ".env.example"

    print("=" * 60)
    print("Configuration Consistency Check")
    print("=" * 60)

    if not model_path.exists():
        print(f"ERROR: Model file not found: {model_path}")
        return 1

    if not env_path.exists():
        print(f"ERROR: .env.example not found: {env_path}")
        return 1

    model_fields = extract_config_fields_from_model(model_path)
    env_fields = extract_config_fields_from_env_example(env_path)

    print(f"\nPydantic model fields: {len(model_fields)}")
    print(f".env.example fields: {len(env_fields)}")

    # Check for fields in model but not in .env.example
    missing_in_env = model_fields - env_fields
    if missing_in_env:
        print(f"\n❌ MISSING in .env.example ({len(missing_in_env)} fields):")
        for field in sorted(missing_in_env):
            print(f"   - {field}")
    else:
        print("\n✅ All model fields are present in .env.example")

    # Check for fields in .env.example but not in model
    extra_in_env = env_fields - model_fields
    if extra_in_env:
        print(f"\n⚠️  EXTRA in .env.example (not in model) ({len(extra_in_env)} fields):")
        reference_index = _build_reference_index(project_root)
        unused_extra: set[str] = set()
        for field in sorted(extra_in_env):
            if field in reference_index:
                print(f"   - {field} (referenced)")
            else:
                print(f"   - {field} (UNUSED)")
                unused_extra.add(field)
    else:
        print("✅ No extra fields in .env.example")

    print("\n" + "=" * 60)

    if missing_in_env:
        print("RESULT: FAILED - Please add missing fields to .env.example")
        return 1

    if extra_in_env:
        reference_index = _build_reference_index(project_root)
        unused_extra = {k for k in extra_in_env if k not in reference_index}
        if unused_extra:
            print("RESULT: FAILED - .env.example contains unused extra fields")
            return 1

    print("RESULT: PASSED - Configuration is synchronized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
