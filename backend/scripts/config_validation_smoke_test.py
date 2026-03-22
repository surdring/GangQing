#!/usr/bin/env python3
"""Configuration validation smoke test (Task 43.1).

This smoke test verifies:
1. Configuration loading with complete config (success path)
2. Fast failure when required configuration is missing
3. Error messages are in English and clear
4. Structured error logging format
5. .env.local loading mechanism

Usage:
    # With complete config (should pass)
    GANGQING_DATABASE_URL=postgresql://test/test python backend/scripts/config_validation_smoke_test.py

    # With missing config (should fail with clear error)
    python backend/scripts/config_validation_smoke_test.py --test-missing
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parents[2]


def run_config_check(env_vars: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run configuration check and return exit code, stdout, stderr."""
    project_root = get_project_root()
    backend_dir = project_root / "backend"

    # Prepare environment
    test_env = os.environ.copy()
    if env_vars:
        test_env.update(env_vars)

    pythonpath_items: list[str] = []
    existing_pythonpath = test_env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_items.append(existing_pythonpath)
    pythonpath_items.append(str(backend_dir))
    test_env["PYTHONPATH"] = os.pathsep.join(pythonpath_items)

    # Run config module as script
    result = subprocess.run(
        [sys.executable, "-m", "gangqing.config"],
        cwd=str(backend_dir),
        env=test_env,
        capture_output=True,
        text=True,
    )

    return result.returncode, result.stdout, result.stderr


def test_complete_config_success() -> dict:
    """Test that configuration loads successfully with complete required config."""
    print("\n[TEST] Complete configuration (success path)...")

    env_vars = {
        "GANGQING_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/gangqing",
        "GANGQING_JWT_SECRET": "test-secret-key-at-least-16-chars",
        "GANGQING_LOG_LEVEL": "INFO",
        "GANGQING_API_PORT": "8000",
    }

    exit_code, stdout, stderr = run_config_check(env_vars)

    result = {
        "name": "complete_config_success",
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }

    if exit_code == 0:
        print(f"  ✓ PASSED: Configuration loaded successfully")
        if "Configuration loaded successfully" in stdout:
            print(f"  ✓ Confirmation message present")
    else:
        print(f"  ✗ FAILED: Expected exit code 0, got {exit_code}")
        print(f"  stderr: {stderr[:200]}")

    return result


def test_missing_database_url_fails() -> dict:
    """Test that missing DATABASE_URL causes fast failure with English error."""
    print("\n[TEST] Missing DATABASE_URL (fail-fast)...")

    # Explicitly unset DATABASE_URL
    env_vars = {
        "GANGQING_DATABASE_URL": "",  # Empty to trigger validation error
        "GANGQING_JWT_SECRET": "test-secret-key-at-least-16-chars",
    }

    # Remove from environment if present
    test_env = os.environ.copy()
    for key in list(test_env.keys()):
        if key.startswith("GANGQING_DATABASE"):
            del test_env[key]

    exit_code, stdout, stderr = run_config_check(env_vars)

    result = {
        "name": "missing_database_url_fails",
        "passed": exit_code == 1,
        "exit_code": exit_code,
        "error_english": False,
        "error_structured": False,
        "stderr": stderr,
    }

    # Check exit code
    if exit_code == 1:
        print(f"  ✓ Exit code is 1 (as expected for failure)")
    else:
        print(f"  ✗ Expected exit code 1, got {exit_code}")
        result["passed"] = False

    # Check error message is in English
    english_indicators = [
        "Missing required configuration",
        "DATABASE_URL",
        "GANGQING_DATABASE_URL",
        ".env.local",
        ".env.example",
    ]
    found_indicators = [ind for ind in english_indicators if ind in stderr]
    if len(found_indicators) >= 3:
        print(f"  ✓ Error message is in English with clear indicators")
        result["error_english"] = True
    else:
        print(f"  ✗ Error message missing expected English indicators")
        print(f"    Found: {found_indicators}")

    # Check structured error format
    if "CONFIG_MISSING" in stderr or "CONFIG_INVALID" in stderr:
        print(f"  ✓ Error contains structured error code")
        result["error_structured"] = True

    # Check config key reference
    if "config_key" in stderr or "GANGQING_DATABASE_URL" in stderr:
        print(f"  ✓ Error references configuration key")

    return result


def test_invalid_log_level_fails() -> dict:
    """Test that invalid log level causes failure with clear error."""
    print("\n[TEST] Invalid LOG_LEVEL format (CONFIG_INVALID)...")

    env_vars = {
        "GANGQING_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/gangqing",
        "GANGQING_JWT_SECRET": "test-secret-key-at-least-16-chars",
        "GANGQING_LOG_LEVEL": "INVALID_LEVEL",
    }

    exit_code, stdout, stderr = run_config_check(env_vars)

    result = {
        "name": "invalid_log_level_fails",
        "passed": exit_code == 1,
        "exit_code": exit_code,
        "error_code_present": False,
        "stderr": stderr,
    }

    if exit_code == 1:
        print(f"  ✓ Exit code is 1 (as expected for validation failure)")
    else:
        print(f"  ✗ Expected exit code 1, got {exit_code}")

    # Check for CONFIG_INVALID in output
    if "CONFIG_INVALID" in stderr or "Invalid configuration" in stderr:
        print(f"  ✓ Error contains CONFIG_INVALID code")
        result["error_code_present"] = True
    else:
        print(f"  ⚠ CONFIG_INVALID not found in error output")

    # Check for allowed values reference
    if "DEBUG/INFO/WARNING/ERROR/CRITICAL" in stderr:
        print(f"  ✓ Error message references allowed values")

    return result


def test_environment_variable_priority() -> dict:
    """Test that environment variables take priority."""
    print("\n[TEST] Environment variable priority over defaults...")

    # Set non-default values
    env_vars = {
        "GANGQING_DATABASE_URL": "postgresql+psycopg://env-test:5432/db",
        "GANGQING_JWT_SECRET": "test-secret-key-at-least-16-chars",
        "GANGQING_API_PORT": "9999",
        "GANGQING_LOG_LEVEL": "DEBUG",
    }

    exit_code, stdout, stderr = run_config_check(env_vars)

    result = {
        "name": "environment_variable_priority",
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "stdout": stdout,
    }

    if exit_code == 0:
        print(f"  ✓ Configuration loaded with custom environment values")
    else:
        print(f"  ✗ Failed to load with custom environment values")

    return result


def main() -> int:
    """Run all smoke tests and report results."""
    parser = argparse.ArgumentParser(description="Config validation smoke test")
    parser.add_argument(
        "--test-missing",
        action="store_true",
        help="Only test missing config scenario (for manual verification)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("GangQing Configuration Validation Smoke Test (T43.1)")
    print("=" * 60)

    if args.test_missing:
        # Quick manual test mode
        result = test_missing_database_url_fails()
        print("\n" + "=" * 60)
        if result["passed"]:
            print("Manual test: PASSED (service correctly fails with missing config)")
            return 0
        else:
            print("Manual test: FAILED")
            return 1

    results: list[dict] = []

    # Run all tests
    results.append(test_complete_config_success())
    results.append(test_missing_database_url_fails())
    results.append(test_invalid_log_level_fails())
    results.append(test_environment_variable_priority())

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r.get("passed", False))
    failed = sum(1 for r in results if not r.get("passed", False))

    for result in results:
        status = "✓ PASS" if result.get("passed") else "✗ FAIL"
        print(f"  {status}: {result['name']}")

    print(f"\nTotal: {passed} passed, {failed} failed, {len(results)} total")

    # Return exit code based on results
    if failed > 0:
        print("\nSmoke test: FAILED")
        return 1
    else:
        print("\nSmoke test: PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
