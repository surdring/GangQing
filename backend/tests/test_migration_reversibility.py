"""Unit tests for migration reversibility guardrails.

These tests enforce the repository migration policy:
- Each Alembic revision file must define both upgrade() and downgrade().

This is a unit test (no DB). The real Postgres rollback cycle is covered by
backend/scripts/postgres_schema_smoke_test.py and
backend/scripts/postgres_migration_rollback_smoke_test.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _parse_module(path: Path) -> ast.Module:
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def _get_function_names(module: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
    return names


def _get_revision_files() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    versions_dir = repo_root / "backend" / "migrations" / "versions"
    if not versions_dir.exists():
        raise RuntimeError("Migrations versions directory is missing")

    files = sorted(p for p in versions_dir.glob("*.py") if p.name != "__init__.py")
    if not files:
        raise RuntimeError("No Alembic revision files found")
    return files


@pytest.mark.parametrize("revision_file", _get_revision_files())
def test_each_revision_has_upgrade_and_downgrade(revision_file: Path) -> None:
    module = _parse_module(revision_file)
    fn_names = _get_function_names(module)

    assert "upgrade" in fn_names, f"Missing upgrade() in {revision_file.name}"
    assert "downgrade" in fn_names, f"Missing downgrade() in {revision_file.name}"
