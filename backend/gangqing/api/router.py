from __future__ import annotations

from fastapi import APIRouter, Depends

from gangqing.api.auth import router as auth_router
from gangqing.api.audit import router as audit_router
from gangqing.api.chat import router as chat_router
from gangqing.api.evidence import router as evidence_router
from gangqing.api.finance import router as finance_router
from gangqing.api.health import router as health_router
from gangqing.api.metrics import router as metrics_router
from gangqing.api.tools_demo import router as tools_demo_router
from gangqing.common.context import build_request_context


def create_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(build_request_context)])
    router.include_router(auth_router)
    router.include_router(health_router)
    router.include_router(chat_router)
    router.include_router(evidence_router)
    router.include_router(audit_router)
    router.include_router(finance_router)
    router.include_router(tools_demo_router)
    router.include_router(metrics_router)
    return router
