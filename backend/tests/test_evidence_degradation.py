from __future__ import annotations

from datetime import datetime, timezone

from gangqing.common.errors import ErrorCode
from gangqing.common.evidence_degradation import evaluate_evidence_degradation
from gangqing_db.evidence import Evidence, EvidenceTimeRange


def _build_evidence(*, evidence_id: str, validation: str) -> Evidence:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return Evidence(
        evidence_id=evidence_id,
        source_system="Postgres",
        source_locator={"tableOrView": "fact_production_daily"},
        time_range=EvidenceTimeRange(
            start=now.replace(hour=0, minute=0, second=0),
            end=now,
        ),
        tool_call_id="tc_1",
        lineage_version=None,
        data_quality_score=None,
        confidence="High",
        validation=validation,
        redactions=None,
    )


def test_degradation_missing_evidence_refs_emits_evidence_missing() -> None:
    decision = evaluate_evidence_degradation(
        tool_call_id="tc_1",
        tool_name="postgres_readonly_query",
        evidence_refs=None,
        evidences=[],
    )

    assert decision.can_output_deterministic_numbers is False
    assert len(decision.warnings) == 1
    assert decision.warnings[0].code == ErrorCode.EVIDENCE_MISSING.value
    assert decision.warnings[0].message
    assert decision.warnings[0].details == {
        "toolCallId": "tc_1",
        "toolName": "postgres_readonly_query",
    }


def test_degradation_mismatch_emits_evidence_mismatch() -> None:
    decision = evaluate_evidence_degradation(
        tool_call_id="tc_1",
        tool_name="postgres_readonly_query",
        evidence_refs=["e1"],
        evidences=[_build_evidence(evidence_id="e1", validation="mismatch")],
    )

    assert decision.can_output_deterministic_numbers is False
    assert [w.code for w in decision.warnings] == [ErrorCode.EVIDENCE_MISMATCH.value]
    assert decision.warnings[0].details["evidenceId"] == "e1"


def test_degradation_out_of_bounds_emits_guardrail_blocked() -> None:
    decision = evaluate_evidence_degradation(
        tool_call_id="tc_1",
        tool_name="postgres_readonly_query",
        evidence_refs=["e1"],
        evidences=[_build_evidence(evidence_id="e1", validation="out_of_bounds")],
    )

    assert decision.can_output_deterministic_numbers is False
    assert [w.code for w in decision.warnings] == [ErrorCode.GUARDRAIL_BLOCKED.value]
    assert decision.warnings[0].details["evidenceId"] == "e1"
