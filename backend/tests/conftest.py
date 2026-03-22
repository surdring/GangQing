from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import pytest

from gangqing.common.settings import reset_settings_cache
from gangqing_db.settings import load_settings


# Ensure local development config is loaded with priority:
# os.environ > repo-root .env.local
load_settings()


@pytest.fixture(autouse=True)
def _reset_common_settings_cache() -> None:
    reset_settings_cache()
