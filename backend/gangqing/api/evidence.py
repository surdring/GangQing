from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gangqing.common.auth import require_authed_request_context
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.rbac import require_capability
from gangqing_db.audit_query import list_tool_call_traces_by_request_id
from gangqing_db.evidence_chain import Citation, EvidenceChain, Lineage
from gangqing_db.evidence_store import list_evidences_by_request_id


router = APIRouter()


class EvidenceChainResponse(BaseModel):
    evidence_chain: EvidenceChain = Field(alias="evidenceChain")

    model_config = {"populate_by_name": True}


@router.get("/evidence/chains/{request_id}", response_model=EvidenceChainResponse)
def get_evidence_chain(
    request: Request,
    request_id: str,
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("evidence:chain:read")),
) -> EvidenceChainResponse:
    if not request_id.strip():
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Validation failed",
            request_id=ctx.request_id,
            details={"path": "requestId"},
            retryable=False,
        )

    evidences = list_evidences_by_request_id(ctx=ctx, request_id=request_id)
    tool_traces = list_tool_call_traces_by_request_id(ctx=ctx, request_id=request_id)

    citations = [
        Citation(
            citationId=f"cite:{e.evidence_id}",
            evidenceId=e.evidence_id,
            sourceSystem=e.source_system,
            sourceLocator=e.source_locator,
            timeRange=e.time_range.model_dump(by_alias=True, mode="json")
            if hasattr(e.time_range, "model_dump")
            else e.time_range,
            extractedAt=(
                str(e.source_locator.get("extractedAt")).strip()
                if isinstance(e.source_locator, dict) and e.source_locator.get("extractedAt") is not None
                else None
            ),
            filtersSummary=(
                e.source_locator.get("filters")
                if isinstance(e.source_locator, dict) and isinstance(e.source_locator.get("filters"), dict)
                else None
            ),
        )
        for e in evidences
    ]

    lineages: list[Lineage] = []
    for e in evidences:
        lineage_version = getattr(e, "lineage_version", None)
        if lineage_version is None:
            continue
        metric_name = None
        if isinstance(e.source_locator, dict):
            raw_metric_name = e.source_locator.get("metricName")
            if isinstance(raw_metric_name, str) and raw_metric_name.strip():
                metric_name = raw_metric_name.strip()
        lineages.append(
            Lineage(
                metricName=metric_name or e.evidence_id,
                lineageVersion=str(lineage_version),
                formulaId=None,
                inputs=[{"evidenceId": e.evidence_id}],
            )
        )

    chain = EvidenceChain(
        requestId=request_id,
        tenantId=ctx.tenant_id,
        projectId=ctx.project_id,
        sessionId=ctx.session_id,
        claims=[],
        evidences=evidences,
        citations=citations,
        lineages=lineages,
        toolTraces=tool_traces,
        warnings=[],
    )
    return EvidenceChainResponse(evidenceChain=chain)
