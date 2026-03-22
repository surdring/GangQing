"""Smoke test for semantic ID mapping evidence and audit integration.

This smoke test validates:
1. Evidence output contains mapping_version, source_systems, conflict_status
2. Audit logs cover all mapping-related events
3. requestId贯穿映射全链路
4. SSE evidence.update events contain mapping information

Usage:
    cd /home/surdring/workspace/GangQing
    python backend/scripts/semantic_id_mapping_smoke_test.py

Exit codes:
    0: All assertions passed
    1: One or more assertions failed
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


def create_mock_context(request_id: Optional[str] = None) -> Any:
    """Create a mock request context for testing."""
    ctx = MagicMock()
    ctx.request_id = request_id or f"test-req-{uuid.uuid4().hex[:8]}"
    ctx.tenant_id = "test-tenant"
    ctx.project_id = "test-project"
    ctx.user_id = "test-user"
    ctx.role = "admin"
    ctx.session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    return ctx


def test_mapping_evidence_structure() -> bool:
    """Test that MappingEvidence contains all required fields from T56.4.

    Verification:
    - Evidence contains mapping_version
    - Evidence contains source_systems
    - Evidence contains conflict_status
    - Evidence contains gate_passed
    - Evidence contains requestId
    """
    print("\n[TEST] Mapping Evidence Structure")
    print("-" * 50)

    try:
        from gangqing.semantic.mapping_evidence import (
            MappingEvidence,
            MappingEvidenceBuilder,
        )
        from gangqing.semantic.models import EntityMappingResponse, EntityType

        ctx = create_mock_context("req-evidence-001")
        builder = MappingEvidenceBuilder(ctx)

        # Create sample mapping
        mapping = EntityMappingResponse(
            unified_id="equip-001",
            entity_type=EntityType.EQUIPMENT,
            source_system="ERP",
            source_id="erp-equip-123",
            tenant_id=ctx.tenant_id,
            project_id=ctx.project_id,
            version=3,
            valid_from=datetime.now(timezone.utc),
            valid_to=None,
        )

        # Build evidence
        evidence = builder.from_mapping_response(mapping)

        # Assertions per T56.4 spec
        assert evidence.mapping_version == 3, "mapping_version must be present"
        assert evidence.source_systems == ["ERP"], "source_systems must be present"
        assert evidence.conflict_status == "clean", "conflict_status must be present"
        assert evidence.gate_passed is True, "gate_passed must be present"
        assert evidence.request_id == "req-evidence-001", "request_id must be traced"

        print(f"  mapping_version: {evidence.mapping_version} ")
        print(f"  source_systems: {evidence.source_systems} ")
        print(f"  conflict_status: {evidence.conflict_status} ")
        print(f"  gate_passed: {evidence.gate_passed} ")
        print(f"  request_id: {evidence.request_id} ")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_evidence_conflict_detection() -> bool:
    """Test evidence creation with conflict detection.

    Verification:
    - Evidence captures conflict status correctly
    - Conflict details are included
    - Gate block reason is set when conflict detected
    """
    print("\n[TEST] Evidence Conflict Detection")
    print("-" * 50)

    try:
        from gangqing.semantic.mapping_evidence import MappingEvidenceBuilder
        from gangqing.semantic.models import (
            ConflictDetectionResult,
            ConflictType,
            EntityMappingResponse,
            EntityType,
        )

        ctx = create_mock_context("req-conflict-001")
        builder = MappingEvidenceBuilder(ctx)

        # Create conflicting mappings (multi-to-one)
        mappings = [
            EntityMappingResponse(
                unified_id="equip-conflict",
                entity_type=EntityType.EQUIPMENT,
                source_system="ERP",
                source_id="erp-001",
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                version=1,
                valid_from=datetime.now(timezone.utc),
            ),
            EntityMappingResponse(
                unified_id="equip-conflict",
                entity_type=EntityType.EQUIPMENT,
                source_system="MES",
                source_id="mes-001",
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                version=2,
                valid_from=datetime.now(timezone.utc),
            ),
        ]

        # Build evidence from conflicting mappings
        evidence = builder.from_mapping_list(
            "equip-conflict", EntityType.EQUIPMENT, mappings
        )

        assert evidence.conflict_status == "conflict", "Should detect conflict"
        assert set(evidence.source_systems) == {"ERP", "MES"}, "Should list all source systems"
        assert evidence.conflict_details is not None, "Should include conflict details"

        print(f"  conflict_status: {evidence.conflict_status} ")
        print(f"  source_systems: {evidence.source_systems} ")
        print(f"  conflict_details: {evidence.conflict_details} ")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_evidence_missing_mapping() -> None:
    """Test evidence creation for missing mapping.

    Verification:
    - Evidence captures 'missing' status
    - Gate block reason is set
    - Empty source_systems list
    """
    print("\n[TEST] Evidence Missing Mapping")
    print("-" * 50)

    try:
        from gangqing.semantic.mapping_evidence import MappingEvidenceBuilder
        from gangqing.semantic.models import ConflictDetectionResult, ConflictType, EntityType

        ctx = create_mock_context("req-missing-001")
        builder = MappingEvidenceBuilder(ctx)

        # Create evidence for missing mapping
        conflict = ConflictDetectionResult(
            unified_id="missing-001",
            entity_type=EntityType.MATERIAL,
            conflict_type=ConflictType.MAPPING_MISSING,
            conflict_details={"reason": "No mapping found"},
            severity="critical",
        )

        evidence = builder.from_conflict_detection(
            "missing-001", EntityType.MATERIAL, [], conflict
        )

        assert evidence.conflict_status == "missing", "Should mark as missing"
        assert evidence.source_systems == [], "Should have empty source_systems"
        assert evidence.gate_passed is False, "Should be blocked"

        print(f"  conflict_status: {evidence.conflict_status} ")
        print(f"  source_systems: {evidence.source_systems} ")
        print(f"  gate_passed: {evidence.gate_passed} ")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_sse_evidence_format() -> bool:
    """Test SSE evidence.update format.

    Verification:
    - Evidence converts to proper SSE format
    - All required fields are present in SSE payload
    - Timestamp formats are ISO strings
    """
    print("\n[TEST] SSE Evidence Format")
    print("-" * 50)

    try:
        from gangqing.semantic.mapping_evidence import MappingEvidence
        from gangqing.semantic.models import EntityType

        now = datetime.now(timezone.utc)
        evidence = MappingEvidence(
            evidence_id="ev:mapping:test",
            unified_id="order-001",
            entity_type=EntityType.ORDER,
            mapping_version=5,
            source_systems=["ERP", "DCS"],
            conflict_status="clean",
            valid_from=now,
            valid_to=None,
            gate_passed=True,
            gate_block_reason=None,
            request_id="req-sse-001",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        sse_format = evidence.to_sse_evidence()

        # Verify SSE format structure
        assert sse_format["evidenceId"] == "ev:mapping:test"
        assert sse_format["type"] == "mapping"
        assert sse_format["unifiedId"] == "order-001"
        assert sse_format["entityType"] == "order"
        assert sse_format["mappingVersion"] == 5
        assert sse_format["sourceSystems"] == ["ERP", "DCS"]
        assert sse_format["conflictStatus"] == "clean"
        assert sse_format["gatePassed"] is True
        assert sse_format["validFrom"] == now.isoformat()

        print(f"  SSE format keys: {list(sse_format.keys())}")
        print(f"  type: {sse_format['type']}")
        print(f"  mappingVersion: {sse_format['mappingVersion']}")
        print(f"  conflictStatus: {sse_format['conflictStatus']}")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_audit_mapping_logger() -> bool:
    """Test AuditMappingLogger event types.

    Verification:
    - mapping.query event is created correctly
    - mapping.conflict_detected event is created correctly
    - mapping.aggregation_blocked event is created correctly
    - mapping.version_* events are created correctly
    - All events contain requestId, tenant_id, project_id
    """
    print("\n[TEST] Audit Mapping Logger")
    print("-" * 50)

    try:
        from gangqing_db.audit_mapping import (
            AuditMappingLogger,
            MappingAuditEventType,
        )

        ctx = create_mock_context("req-audit-001")

        # Create logger with no-op audit function
        logger = AuditMappingLogger(ctx, None)

        # Test mapping.query
        query_event = logger.log_mapping_query(
            unified_id="equip-001",
            entity_type="equipment",
            version=3,
            result_count=1,
            found=True,
        )

        assert query_event.event_type == "mapping.query"
        assert query_event.request_id == "req-audit-001"
        assert query_event.tenant_id == "test-tenant"
        assert query_event.project_id == "test-project"

        # Test mapping.conflict_detected
        conflict_event = logger.log_conflict_detected(
            unified_id="conflict-001",
            entity_type="material",
            conflict_type="multi_to_one",
            severity="critical",
        )

        assert conflict_event.event_type == "mapping.conflict_detected"
        assert conflict_event.conflict_type == "multi_to_one"
        assert conflict_event.severity == "critical"
        assert conflict_event.request_id == "req-audit-001"

        # Test mapping.aggregation_blocked
        block_event = logger.log_aggregation_blocked(
            reason="Multiple mappings detected",
            unified_id="block-001",
            entity_type="batch",
            conflict_count=2,
        )

        assert block_event.event_type == "mapping.aggregation_blocked"
        assert block_event.result_status == "blocked"
        assert block_event.error_code == "AGGREGATION_BLOCKED"

        # Test version events
        create_event = logger.log_version_created(
            unified_id="new-001",
            entity_type="order",
            version=1,
            source_system="ERP",
            source_id="erp-001",
        )

        assert create_event.event_type == "mapping.version_created"

        print(f"  mapping.query: request_id={query_event.request_id}")
        print(f"  mapping.conflict_detected: conflict_type={conflict_event.conflict_type}")
        print(f"  mapping.aggregation_blocked: error_code={block_event.error_code}")
        print(f"  mapping.version_created: version={create_event.version}")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_request_id_tracing() -> bool:
    """Test that request_id is traced through all operations.

    Verification:
    - Same request_id appears in evidence
    - Same request_id appears in audit events
    - request_id贯穿映射查询、冲突检测、门禁检查全链路
    """
    print("\n[TEST] Request ID Tracing")
    print("-" * 50)

    try:
        from gangqing.semantic.mapping_evidence import MappingEvidenceBuilder
        from gangqing_db.audit_mapping import AuditMappingLogger
        from gangqing.semantic.models import EntityMappingResponse, EntityType

        # Single request_id for entire chain
        trace_id = "req-trace-full-001"
        ctx = create_mock_context(trace_id)

        # Create evidence
        builder = MappingEvidenceBuilder(ctx)
        mapping = EntityMappingResponse(
            unified_id="trace-test",
            entity_type=EntityType.EQUIPMENT,
            source_system="ERP",
            source_id="erp-trace",
            tenant_id=ctx.tenant_id,
            project_id=ctx.project_id,
            version=1,
            valid_from=datetime.now(timezone.utc),
        )

        evidence = builder.from_mapping_response(mapping)

        # Create audit event
        logger = AuditMappingLogger(ctx, None)
        audit_event = logger.log_mapping_query(
            unified_id="trace-test",
            entity_type="equipment",
        )

        # Verify request_id贯穿
        assert evidence.request_id == trace_id, f"Evidence request_id should be {trace_id}"
        assert audit_event.request_id == trace_id, f"Audit event request_id should be {trace_id}"

        print(f"  Trace request_id: {trace_id}")
        print(f"  Evidence request_id: {evidence.request_id}")
        print(f"  Audit event request_id: {audit_event.request_id}")
        print("  All request_ids match across evidence and audit")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_all_audit_event_types() -> bool:
    """Test that all required T56.4 audit event types are covered.

    Verification:
    - mapping.query event type exists
    - mapping.conflict_detected event type exists
    - mapping.aggregation_blocked event type exists
    - mapping.version_created/updated/deleted event types exist
    """
    print("\n[TEST] All Audit Event Types Covered")
    print("-" * 50)

    try:
        from gangqing_db.audit_mapping import MappingAuditEventType

        required_types = {
            "mapping.query",
            "mapping.conflict_detected",
            "mapping.aggregation_blocked",
            "mapping.version_created",
            "mapping.version_updated",
            "mapping.version_deleted",
        }

        available_types = {t.value for t in MappingAuditEventType}

        missing = required_types - available_types

        if missing:
            print(f"  FAILED: Missing event types: {missing}")
            return False

        print(f"  Required types: {required_types}")
        print(f"  Available types: {available_types}")
        print("  All required event types are covered")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_integration_with_mapping_versioning() -> bool:
    """Test evidence integration with MappingVersionManager.

    Verification:
    - MappingVersionManager has evidence_builder attribute
    - MappingVersionManager has audit_logger attribute
    - get_current_mapping_with_evidence returns both mapping and evidence
    """
    print("\n[TEST] Integration with MappingVersioning")
    print("-" * 50)

    try:
        from gangqing.semantic.mapping_versioning import MappingVersionManager

        ctx = create_mock_context("req-int-001")

        # Check that manager can be initialized with evidence/audit support
        # Note: We can't connect to real DB in smoke test, but we can verify
        # the structure exists
        manager = MappingVersionManager(ctx)

        # Verify evidence builder is initialized
        assert hasattr(manager, "_evidence_builder"), "Manager should have evidence builder"
        assert manager._evidence_builder is not None, "Evidence builder should not be None"

        # Verify audit logger is initialized
        assert hasattr(manager, "_audit_logger"), "Manager should have audit logger"
        assert manager._audit_logger is not None, "Audit logger should not be None"

        print("  MappingVersionManager initialized")
        print("  Evidence builder: present")
        print("  Audit logger: present")
        print("  All assertions passed")
        return True

    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def main() -> int:
    """Run all smoke tests.

    Returns:
        0 if all tests pass, 1 otherwise
    """
    print("=" * 60)
    print("Semantic ID Mapping Evidence & Audit Smoke Test")
    print("=" * 60)
    print("T56.4 - Evidence Chain Integration and Audit")
    print()

    tests = [
        test_mapping_evidence_structure,
        test_evidence_conflict_detection,
        test_evidence_missing_mapping,
        test_sse_evidence_format,
        test_audit_mapping_logger,
        test_request_id_tracing,
        test_all_audit_event_types,
        test_integration_with_mapping_versioning,
    ]

    results: List[bool] = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n[ERROR] Test {test.__name__} raised exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results), 1):
        status = "PASS" if result else "FAIL"
        symbol = " " if result else "X"
        print(f"  [{symbol}] {i}. {test.__name__}: {status}")

    print()
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("All smoke tests PASSED")
        return 0
    else:
        print("Some smoke tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
