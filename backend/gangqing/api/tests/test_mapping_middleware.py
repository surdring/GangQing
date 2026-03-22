"""Unit tests for API middleware mapping gate.

Tests cover:
1. require_valid_mapping dependency factory
2. require_valid_mappings_for_refs dependency factory
3. HTTP exception creation for blocked aggregation
4. Response building for aggregation blocked errors
5. Context extraction from request state
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import State

from gangqing.common.context import RequestContext
from gangqing.common.errors import ErrorCode
from gangqing.api.middleware.mapping_gate import (
    MappingGateMiddleware,
    build_aggregation_blocked_response,
    get_request_context,
    _create_http_exception,
    require_valid_mapping,
    require_valid_mappings_for_refs,
)
from gangqing.semantic.aggregation_gate import (
    AggregationGateResult,
    EntityRef,
)
from gangqing.semantic.models import ConflictDetectionResult, ConflictType, EntityType


# Fixtures
@pytest.fixture
def test_tenant_id() -> str:
    """Generate unique test tenant ID."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_project_id() -> str:
    """Generate unique test project ID."""
    return f"test-project-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_request_id() -> str:
    """Generate unique test request ID."""
    return f"req-{uuid.uuid4().hex[:16]}"


@pytest.fixture
def request_context(
    test_tenant_id: str,
    test_project_id: str,
    test_request_id: str,
) -> RequestContext:
    """Create test request context."""
    return RequestContext(
        tenant_id=test_tenant_id,
        project_id=test_project_id,
        request_id=test_request_id,
        user_id="test-user",
        role="admin",
    )


@pytest.fixture
def mock_request(request_context: RequestContext) -> MagicMock:
    """Create mock FastAPI request with context in state."""
    mock = MagicMock(spec=Request)
    mock.state = State()
    mock.state.request_context = request_context
    mock.path_params = {}
    mock.query_params = {}
    return mock


# Tests for get_request_context
class TestGetRequestContext:
    """Test request context extraction."""

    @pytest.mark.asyncio
    async def test_context_found(self, mock_request: MagicMock) -> None:
        """Test successful context extraction."""
        ctx = await get_request_context(mock_request)
        assert ctx is not None
        assert ctx.request_id == mock_request.state.request_context.request_id

    @pytest.mark.asyncio
    async def test_context_not_found(self) -> None:
        """Test error when context not found."""
        mock = MagicMock(spec=Request)
        mock.state = State()  # No request_context set

        with pytest.raises(HTTPException) as exc_info:
            await get_request_context(mock)

        assert exc_info.value.status_code == 500


# Tests for require_valid_mapping
class TestRequireValidMapping:
    """Test require_valid_mapping dependency factory."""

    @pytest.mark.asyncio
    @patch("gangqing.api.middleware.mapping_gate.MappingVersionManager")
    @patch("gangqing.api.middleware.mapping_gate.AggregationGate")
    async def test_valid_mapping_allows_request(
        self,
        mock_gate_class: Mock,
        mock_manager_class: Mock,
        mock_request: MagicMock,
        request_context: RequestContext,
    ) -> None:
        """Test valid mapping allows request to proceed."""
        # Arrange: Valid mapping result
        mock_request.path_params = {"unified_id": "EQUIP-001"}

        mock_gate = MagicMock()
        mock_gate.check_single_entity.return_value = AggregationGateResult(
            allowed=True,
            entity_refs=[EntityRef("EQUIP-001", EntityType.EQUIPMENT)],
        )
        mock_gate_class.return_value = mock_gate

        # Create dependency
        dependency = require_valid_mapping(
            entity_type=EntityType.EQUIPMENT,
            unified_id_param="unified_id",
        )

        # Execute dependency
        result = await dependency(mock_request, request_context, mock_manager_class.return_value)

        # Assert
        assert result.allowed is True

    @pytest.mark.asyncio
    @patch("gangqing.api.middleware.mapping_gate.MappingVersionManager")
    @patch("gangqing.api.middleware.mapping_gate.AggregationGate")
    async def test_invalid_mapping_blocks_request(
        self,
        mock_gate_class: Mock,
        mock_manager_class: Mock,
        mock_request: MagicMock,
        request_context: RequestContext,
    ) -> None:
        """Test invalid mapping blocks request with 403."""
        # Arrange: Blocked mapping result
        mock_request.path_params = {"unified_id": "EQUIP-001"}

        mock_gate = MagicMock()
        mock_gate.check_single_entity.return_value = AggregationGateResult(
            allowed=False,
            blocked_reason="Mapping conflict detected",
            conflicts=[
                ConflictDetectionResult(
                    unified_id="EQUIP-001",
                    entity_type=EntityType.EQUIPMENT,
                    conflict_type=ConflictType.MAPPING_MISSING,
                    conflict_details={},
                    severity="critical",
                    request_id=request_context.request_id,
                )
            ],
            entity_refs=[EntityRef("EQUIP-001", EntityType.EQUIPMENT)],
        )
        mock_gate_class.return_value = mock_gate

        # Create dependency
        dependency = require_valid_mapping(
            entity_type=EntityType.EQUIPMENT,
            unified_id_param="unified_id",
        )

        # Act/Assert: Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, request_context, mock_manager_class.return_value)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == ErrorCode.AGGREGATION_BLOCKED.value
        assert "requestId" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("gangqing.api.middleware.mapping_gate.MappingVersionManager")
    async def test_missing_unified_id_parameter(
        self,
        mock_manager_class: Mock,
        mock_request: MagicMock,
        request_context: RequestContext,
    ) -> None:
        """Test validation error when unified_id parameter is missing."""
        # Arrange: No unified_id in path or query params
        mock_request.path_params = {}
        mock_request.query_params = {}

        # Create dependency
        dependency = require_valid_mapping(
            entity_type=EntityType.EQUIPMENT,
            unified_id_param="unified_id",
        )

        # Act/Assert: Should raise HTTPException with 400
        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, request_context, mock_manager_class.return_value)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "requestId" in exc_info.value.detail


# Tests for require_valid_mappings_for_refs
class TestRequireValidMappingsForRefs:
    """Test require_valid_mappings_for_refs dependency factory."""

    @pytest.mark.asyncio
    @patch("gangqing.api.middleware.mapping_gate.MappingVersionManager")
    @patch("gangqing.api.middleware.mapping_gate.AggregationGate")
    async def test_valid_mappings_allows_request(
        self,
        mock_gate_class: Mock,
        mock_manager_class: Mock,
        mock_request: MagicMock,
        request_context: RequestContext,
    ) -> None:
        """Test valid mappings allow request."""
        # Arrange: Extractor returns valid refs
        def extractor(request: Request) -> List[EntityRef]:
            return [
                EntityRef("EQUIP-001", EntityType.EQUIPMENT),
                EntityRef("EQUIP-002", EntityType.EQUIPMENT),
            ]

        mock_gate = MagicMock()
        mock_gate.check_aggregation_prerequisites.return_value = AggregationGateResult(
            allowed=True,
            entity_refs=[
                EntityRef("EQUIP-001", EntityType.EQUIPMENT),
                EntityRef("EQUIP-002", EntityType.EQUIPMENT),
            ],
        )
        mock_gate_class.return_value = mock_gate

        # Create dependency
        dependency = require_valid_mappings_for_refs(extractor)

        # Execute
        result = await dependency(mock_request, request_context, mock_manager_class.return_value)

        # Assert
        assert result.allowed is True

    @pytest.mark.asyncio
    @patch("gangqing.api.middleware.mapping_gate.MappingVersionManager")
    @patch("gangqing.api.middleware.mapping_gate.AggregationGate")
    async def test_invalid_mappings_blocks_request(
        self,
        mock_gate_class: Mock,
        mock_manager_class: Mock,
        mock_request: MagicMock,
        request_context: RequestContext,
    ) -> None:
        """Test invalid mappings block request."""
        # Arrange: Extractor returns refs with conflict
        def extractor(request: Request) -> List[EntityRef]:
            return [EntityRef("EQUIP-001", EntityType.EQUIPMENT)]

        mock_gate = MagicMock()
        mock_gate.check_aggregation_prerequisites.return_value = AggregationGateResult(
            allowed=False,
            blocked_reason="Mapping conflict",
            conflicts=[
                ConflictDetectionResult(
                    unified_id="EQUIP-001",
                    entity_type=EntityType.EQUIPMENT,
                    conflict_type=ConflictType.MAPPING_MISSING,
                    conflict_details={},
                    severity="critical",
                    request_id=request_context.request_id,
                )
            ],
            entity_refs=[EntityRef("EQUIP-001", EntityType.EQUIPMENT)],
        )
        mock_gate_class.return_value = mock_gate

        # Create dependency
        dependency = require_valid_mappings_for_refs(extractor)

        # Act/Assert
        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, request_context, mock_manager_class.return_value)

        assert exc_info.value.status_code == 403


# Tests for _create_http_exception
class TestCreateHttpException:
    """Test HTTP exception creation."""

    def test_exception_with_details(self, test_request_id: str) -> None:
        """Test exception includes all details."""
        result = AggregationGateResult(
            allowed=False,
            blocked_reason="Test block reason",
            conflicts=[],
            entity_refs=[EntityRef("E1", EntityType.EQUIPMENT)],
        )

        exc = _create_http_exception(result, test_request_id)

        assert exc.status_code == 403
        assert exc.detail["code"] == ErrorCode.AGGREGATION_BLOCKED.value
        assert exc.detail["message"] == "Test block reason"
        assert exc.detail["requestId"] == test_request_id
        assert exc.detail["retryable"] is False
        assert "details" in exc.detail

    def test_exception_default_reason(self, test_request_id: str) -> None:
        """Test exception with default reason."""
        result = AggregationGateResult(
            allowed=False,
            blocked_reason=None,
            conflicts=[],
            entity_refs=[],
        )

        exc = _create_http_exception(result, test_request_id)

        assert "Aggregation blocked" in exc.detail["message"]


# Tests for build_aggregation_blocked_response
class TestBuildAggregationBlockedResponse:
    """Test response builder."""

    def test_response_structure(self) -> None:
        """Test response has correct structure."""
        from gangqing.semantic.aggregation_gate import AggregationBlockedError

        error = AggregationBlockedError(
            entity_refs=[EntityRef("E1", EntityType.EQUIPMENT)],
            conflicts=[
                ConflictDetectionResult(
                    unified_id="E1",
                    entity_type=EntityType.EQUIPMENT,
                    conflict_type=ConflictType.MAPPING_MISSING,
                    conflict_details={},
                    severity="critical",
                )
            ],
            request_id="test-req",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        response = build_aggregation_blocked_response(error)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 403

        content = response.body
        if hasattr(content, "decode"):
            import json
            data = json.loads(content.decode())
        else:
            data = content

        assert data["code"] == ErrorCode.AGGREGATION_BLOCKED.value
        assert "message" in data
        assert data["retryable"] is False
        assert data["requestId"] == "test-req"


# Tests for MappingGateMiddleware
class TestMappingGateMiddleware:
    """Test MappingGateMiddleware."""

    def test_should_check_all_paths_by_default(self) -> None:
        """Test middleware checks all paths by default."""
        middleware = MappingGateMiddleware(
            None,  # type: ignore[arg-type]
            protected_paths=[],
            exclude_paths=[],
        )

        assert middleware._should_check("/api/v1/data") is True
        assert middleware._should_check("/any/path") is True

    def test_should_check_protected_paths(self) -> None:
        """Test middleware only checks protected paths when specified."""
        middleware = MappingGateMiddleware(
            None,  # type: ignore[arg-type]
            protected_paths=["/api/v1/aggregate"],
            exclude_paths=[],
        )

        assert middleware._should_check("/api/v1/aggregate/data") is True
        assert middleware._should_check("/api/v1/other") is False

    def test_should_check_excludes_paths(self) -> None:
        """Test middleware excludes specified paths."""
        middleware = MappingGateMiddleware(
            None,  # type: ignore[arg-type]
            protected_paths=[],
            exclude_paths=["/health", "/metrics"],
        )

        assert middleware._should_check("/health/check") is False
        assert middleware._should_check("/metrics/stats") is False
        assert middleware._should_check("/api/data") is True

    def test_should_check_excludes_override_protected(self) -> None:
        """Test exclusions override protected paths."""
        middleware = MappingGateMiddleware(
            None,  # type: ignore[arg-type]
            protected_paths=["/api"],
            exclude_paths=["/api/health"],
        )

        assert middleware._should_check("/api/data") is True
        assert middleware._should_check("/api/health") is False


# Integration-style tests
class TestIntegration:
    """Integration-style tests for middleware components."""

    def test_full_error_flow(self, test_request_id: str) -> None:
        """Test full error flow from gate to response."""
        from gangqing.semantic.aggregation_gate import AggregationBlockedError

        # Create blocked error
        error = AggregationBlockedError(
            entity_refs=[
                EntityRef("EQUIP-001", EntityType.EQUIPMENT),
                EntityRef("EQUIP-002", EntityType.EQUIPMENT),
            ],
            conflicts=[
                ConflictDetectionResult(
                    unified_id="EQUIP-001",
                    entity_type=EntityType.EQUIPMENT,
                    conflict_type=ConflictType.MAPPING_MISSING,
                    conflict_details={"reason": "No mapping"},
                    severity="critical",
                ),
                ConflictDetectionResult(
                    unified_id="EQUIP-002",
                    entity_type=EntityType.EQUIPMENT,
                    conflict_type=ConflictType.MULTI_TO_ONE,
                    conflict_details={"source_systems": ["ERP", "MES"]},
                    severity="critical",
                ),
            ],
            request_id=test_request_id,
            tenant_id="tenant-1",
            project_id="project-1",
        )

        # Convert to HTTP response
        response = build_aggregation_blocked_response(error)

        # Verify response
        assert response.status_code == 403
        content = response.body
        if hasattr(content, "decode"):
            import json
            data = json.loads(content.decode())
        else:
            data = content

        assert data["code"] == "AGGREGATION_BLOCKED"
        assert data["requestId"] == test_request_id
        assert data["retryable"] is False
        assert "EQUIP-001" in str(data["details"])
        assert "EQUIP-002" in str(data["details"])
