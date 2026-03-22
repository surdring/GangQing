from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gangqing.common.errors import ErrorCode
from gangqing_db.evidence import Evidence, EvidenceTimeRange
from gangqing_db.evidence_chain import (
    Claim,
    EvidenceChain,
    merge_evidence_update,
    validate_evidence_chain,
)


def _dt(hours_ago: int) -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)  # stable enough for tests


def _build_evidence(*, evidence_id: str, validation: str, lineage_version: str | None = None) -> Evidence:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return Evidence(
        evidence_id=evidence_id,
        source_system="Postgres",
        source_locator={"tableOrView": "fact_production_daily"},
        time_range=EvidenceTimeRange(start=now.replace(hour=0, minute=0, second=0), end=now),
        tool_call_id="tc_1",
        lineage_version=lineage_version,
        data_quality_score=None,
        confidence="High",
        validation=validation,
        redactions=None,
    )


def test_validate_evidence_chain_happy_path_numeric_claim_ok() -> None:
    chain = EvidenceChain(
        request_id="rid_1",
        tenant_id="t1",
        project_id="p1",
        session_id=None,
        claims=[
            Claim(
                claim_id="c1",
                claim_type="number",
                subject="BlastFurnace#2",
                value=1.23,
                unit="t",
                evidence_refs=["e1"],
                lineage_version=None,
                is_computed=False,
                validation="verifiable",
            )
        ],
        evidences=[_build_evidence(evidence_id="e1", validation="verifiable")],
        warnings=[],
    )

    result = validate_evidence_chain(chain=chain)
    assert result.can_output_deterministic_numbers is True
    assert result.evidence_chain.warnings == []
    assert result.evidence_chain.claims[0].validation == "verifiable"


def test_validate_evidence_chain_missing_evidence_refs_blocks_numbers() -> None:
    chain = EvidenceChain(
        request_id="rid_2",
        tenant_id="t1",
        project_id="p1",
        session_id=None,
        claims=[
            Claim(
                claim_id="c1",
                claim_type="number",
                subject="BlastFurnace#2",
                value=1.23,
                unit="t",
                evidence_refs=[],
                lineage_version=None,
                is_computed=False,
                validation="verifiable",
            )
        ],
        evidences=[],
        warnings=[],
    )

    result = validate_evidence_chain(chain=chain)
    assert result.can_output_deterministic_numbers is False
    assert result.evidence_chain.claims[0].validation == "not_verifiable"
    assert len(result.evidence_chain.warnings) == 1
    w = result.evidence_chain.warnings[0]
    assert w.code == ErrorCode.EVIDENCE_MISSING.value
    assert w.request_id == "rid_2"
    assert isinstance(w.message, str) and w.message


def test_validate_evidence_chain_missing_lineage_version_for_computed_claim_blocks_numbers() -> None:
    chain = EvidenceChain(
        request_id="rid_3",
        tenant_id="t1",
        project_id="p1",
        session_id=None,
        claims=[
            Claim(
                claim_id="c1",
                claim_type="number",
                subject="CostPerTon",
                value=100.0,
                unit="CNY/t",
                evidence_refs=["e1"],
                lineage_version=None,
                is_computed=True,
                validation="verifiable",
            )
        ],
        evidences=[_build_evidence(evidence_id="e1", validation="verifiable")],
        warnings=[],
    )

    result = validate_evidence_chain(chain=chain)
    assert result.can_output_deterministic_numbers is False
    assert result.evidence_chain.claims[0].validation == "not_verifiable"
    assert any(w.code == ErrorCode.EVIDENCE_MISSING.value for w in result.evidence_chain.warnings)


def test_validate_evidence_chain_evidence_mismatch_downgrades_claim() -> None:
    chain = EvidenceChain(
        request_id="rid_4",
        tenant_id="t1",
        project_id="p1",
        session_id=None,
        claims=[
            Claim(
                claim_id="c1",
                claim_type="number",
                subject="BlastFurnace#2",
                value=1.23,
                unit="t",
                evidence_refs=["e1"],
                lineage_version=None,
                is_computed=False,
                validation="verifiable",
            )
        ],
        evidences=[_build_evidence(evidence_id="e1", validation="mismatch")],
        warnings=[],
    )

    result = validate_evidence_chain(chain=chain)
    assert result.can_output_deterministic_numbers is False
    assert result.evidence_chain.claims[0].validation == "mismatch"
    assert any(w.code == ErrorCode.EVIDENCE_MISMATCH.value for w in result.evidence_chain.warnings)


def test_merge_evidence_update_allows_field_completion_and_redactions_append() -> None:
    existing = _build_evidence(evidence_id="e1", validation="not_verifiable", lineage_version=None)
    existing.data_quality_score = None
    existing.redactions = {"pii": "masked"}

    update = _build_evidence(evidence_id="e1", validation="verifiable", lineage_version="lv1")
    update.data_quality_score = 0.9
    update.redactions = {"secrets": "masked"}

    merged, warnings = merge_evidence_update(request_id="rid_merge_1", existing=existing, update=update)
    assert merged.evidence_id == "e1"
    assert merged.lineage_version == "lv1"
    assert merged.data_quality_score == 0.9
    assert merged.validation == "verifiable"
    assert merged.redactions == {"pii": "masked", "secrets": "masked"}
    assert warnings == []


def test_merge_evidence_update_does_not_allow_source_mutation_and_emits_warning() -> None:
    existing = _build_evidence(evidence_id="e1", validation="verifiable", lineage_version=None)
    update = _build_evidence(evidence_id="e1", validation="verifiable", lineage_version=None)
    update.source_system = "Manual"

    merged, warnings = merge_evidence_update(request_id="rid_merge_2", existing=existing, update=update)
    assert merged.source_system == existing.source_system
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.EVIDENCE_MISMATCH.value
    assert warnings[0].request_id == "rid_merge_2"


def test_merge_evidence_update_blocks_validation_regression_from_verifiable() -> None:
    existing = _build_evidence(evidence_id="e1", validation="verifiable", lineage_version=None)
    update = _build_evidence(evidence_id="e1", validation="not_verifiable", lineage_version=None)

    merged, warnings = merge_evidence_update(request_id="rid_merge_3", existing=existing, update=update)
    assert merged.validation == "verifiable"
    assert any(w.code == ErrorCode.EVIDENCE_MISMATCH.value for w in warnings)
