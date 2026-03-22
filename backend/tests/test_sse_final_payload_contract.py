from __future__ import annotations

import pytest
from pydantic import ValidationError

from gangqing.schemas.sse import SseFinalPayload


def test_sse_final_payload_allows_only_status() -> None:
    payload = SseFinalPayload.model_validate({"status": "success"})
    assert payload.status == "success"


def test_sse_final_payload_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _ = SseFinalPayload.model_validate({"status": "success", "done": True})
