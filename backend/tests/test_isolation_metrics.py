from __future__ import annotations

from gangqing.common.context import RequestContext
from gangqing.common.metrics import METRICS
from gangqing.common.errors import AppError
from gangqing.tools.isolation import resolve_scope


def test_isolation_failure_increments_metrics_counter() -> None:
    before = METRICS.snapshot()["http"].get("isolationFailures") or {}
    before_missing = int(before.get("missing_scope", 0))

    ctx = RequestContext(requestId="rid_iso_m_1", tenantId="", projectId="")
    try:
        resolve_scope(ctx=ctx, tenant_id=None, project_id=None)
    except AppError:
        pass

    after = METRICS.snapshot()["http"].get("isolationFailures") or {}
    assert int(after.get("missing_scope", 0)) == before_missing + 1
