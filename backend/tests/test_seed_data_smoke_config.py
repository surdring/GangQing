from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add backend and scripts to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
for _p in (str(_BACKEND_DIR), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gangqing_db.errors import ConfigMissingError, ErrorCode, MigrationError

import seed_data_smoke_test


def test_env_int_invalid_must_fail_with_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GANGQING_SEED", "not-an-int")

    with pytest.raises(MigrationError) as exc_info:
        seed_data_smoke_test._env_int("GANGQING_SEED", default=123, request_id="run-1")

    err = exc_info.value
    assert err.code == ErrorCode.VALIDATION_ERROR
    assert err.message.isascii()
    assert err.request_id == "run-1"


def test_parse_date_invalid_must_fail_with_request_id() -> None:
    with pytest.raises(MigrationError) as exc_info:
        seed_data_smoke_test._parse_date("2026/02/01", request_id="run-2")

    err = exc_info.value
    assert err.code == ErrorCode.VALIDATION_ERROR
    assert err.message.isascii()
    assert err.request_id == "run-2"


def test_require_database_url_missing_must_fail_with_request_id() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("gangqing_db.settings._load_dotenv_file", return_value=None):
            with pytest.raises(ConfigMissingError) as exc_info:
                seed_data_smoke_test._require_database_url(request_id="run-3")

    err = exc_info.value
    assert err.code.value == "CONFIG_MISSING"
    assert err.message.isascii()
    assert err.request_id == "run-3"
    assert "GANGQING_DATABASE_URL" in err.message
