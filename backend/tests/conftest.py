from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing_db.settings import load_settings


# Ensure local development config is loaded with priority:
# os.environ > repo-root .env.local
load_settings()
