"""API layer middleware for mapping aggregation gate.

This module provides FastAPI dependency functions and middleware
for enforcing mapping consistency checks at the API layer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from gangqing.common.context import RequestContext
from gangqing.common.errors import ErrorCode
from gangqing.semantic.aggregation_gate import (
    AggregationBlockedError,
    AggregationGate,
    AggregationGateResult,
    EntityRef,
    MappingVersionManagerProtocol,
)
from gangqing.semantic.mapping_versioning import MappingVersionManager
from gangqing.semantic.models import EntityType


async def get_request_context(request: Request) -> RequestContext:
    """Extract request context from request state.

    This dependency retrieves the RequestContext that should have been
    set by upstream middleware during request processing.

    Args:
        request: FastAPI request object

    Returns:
        RequestContext from request state

    Raises:
        HTTPException: If request context is not found
    """
    ctx = getattr(request.state, "request_context", None)
    if ctx is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Request context not found in request state",
                "retryable": False,
            },
        )
    return ctx


async def get_mapping_manager(
    ctx: RequestContext = Depends(get_request_context),
) -> MappingVersionManager:
    """Dependency to get MappingVersionManager instance.

    Args:
        ctx: RequestContext from dependency

    Returns:
        MappingVersionManager initialized with context
    """
    return MappingVersionManager(ctx)


def require_valid_mapping(
    entity_type: EntityType,
    unified_id_param: str = "unified_id",
    required_source_systems: Optional[List[str]] = None,
) -> Callable:
    """Create a dependency that requires valid mapping for aggregation.

    This dependency function factory creates FastAPI dependencies that:
    1. Extract unified_id from request parameters
    2. Check mapping consistency via AggregationGate
    3. Block request if any conflicts detected

    Usage:
        @app.get("/api/v1/aggregate/{unified_id}")
        async def aggregate_data(
            unified_id: str,
            result: AggregationGateResult = Depends(
                require_valid_mapping(
                    entity_type=EntityType.EQUIPMENT,
                    unified_id_param="unified_id",
                    required_source_systems=["ERP", "MES"],
                )
            ),
        ):
            # If we reach here, mapping is valid
            return {"data": ...}

    Args:
        entity_type: Entity type to check
        unified_id_param: Name of path/query parameter containing unified_id
        required_source_systems: Optional list of required source systems

    Returns:
        Dependency function for FastAPI
    """
    async def check_mapping(
        request: Request,
        ctx: RequestContext = Depends(get_request_context),
        manager: MappingVersionManager = Depends(get_mapping_manager),
    ) -> AggregationGateResult:
        """Execute mapping check."""
        # Extract unified_id from path or query parameters
        unified_id = request.path_params.get(unified_id_param) or request.query_params.get(unified_id_param)

        if not unified_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": f"Missing required parameter: {unified_id_param}",
                    "retryable": False,
                    "requestId": ctx.request_id,
                },
            )

        # Create aggregation gate and check
        gate = AggregationGate(ctx, manager)

        result = gate.check_single_entity(
            unified_id=unified_id,
            entity_type=entity_type,
            required_source_systems=required_source_systems,
        )

        if result.is_blocked:
            # Convert to HTTPException with structured error
            raise _create_http_exception(result, ctx.request_id)

        return result

    return check_mapping


def require_valid_mappings_for_refs(
    entity_refs_extractor: Callable[[Request], List[EntityRef]],
) -> Callable:
    """Create dependency that requires valid mappings for extracted entity refs.

    This is a more flexible dependency factory that allows custom extraction
    of entity references from the request.

    Usage:
        def extract_refs(request: Request) -> List[EntityRef]:
            data = await request.json()
            return [
                EntityRef(
                    unified_id=e["unified_id"],
                    entity_type=EntityType(e["entity_type"]),
                )
                for e in data["entities"]
            ]

        @app.post("/api/v1/aggregate-batch")
        async def aggregate_batch(
            result: AggregationGateResult = Depends(
                require_valid_mappings_for_refs(extract_refs)
            ),
        ):
            # If we reach here, all mappings are valid
            return {"data": ...}

    Args:
        entity_refs_extractor: Callable that extracts List[EntityRef] from Request

    Returns:
        Dependency function for FastAPI
    """
    async def check_mappings(
        request: Request,
        ctx: RequestContext = Depends(get_request_context),
        manager: MappingVersionManager = Depends(get_mapping_manager),
    ) -> AggregationGateResult:
        """Execute batch mapping check."""
        # Extract entity refs using provided extractor
        entity_refs = entity_refs_extractor(request)

        if not entity_refs:
            # Empty refs is allowed
            return AggregationGateResult(allowed=True, entity_refs=[])

        # Create aggregation gate and check
        gate = AggregationGate(ctx, manager)

        result = gate.check_aggregation_prerequisites(entity_refs)

        if result.is_blocked:
            raise _create_http_exception(result, ctx.request_id)

        return result

    return check_mappings


def _create_http_exception(
    result: AggregationGateResult,
    request_id: str,
) -> HTTPException:
    """Create HTTPException from blocked aggregation result.

    Args:
        result: Aggregation gate result with conflicts
        request_id: Request ID for tracing

    Returns:
        HTTPException with structured error response
    """
    return HTTPException(
        status_code=403,
        detail={
            "code": ErrorCode.AGGREGATION_BLOCKED.value,
            "message": result.blocked_reason or "Aggregation blocked due to mapping inconsistency",
            "details": result.to_dict(),
            "retryable": False,
            "requestId": request_id,
        },
    )


class MappingGateMiddleware:
    """Middleware for automatic mapping gate enforcement.

    This middleware can be registered to automatically check
    mapping consistency for specific routes or route patterns.

    Note: This is typically used as a base class or reference
    for implementing route-specific gate checks.
    """

    def __init__(
        self,
        app,
        *,
        protected_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
    ) -> None:
        """Initialize middleware.

        Args:
            app: ASGI application
            protected_paths: List of path prefixes to protect (None = all)
            exclude_paths: List of path prefixes to exclude
        """
        self.app = app
        self.protected_paths = protected_paths or []
        self.exclude_paths = exclude_paths or []

    async def __call__(self, scope, receive, send):
        """ASGI middleware interface."""
        # This is a base implementation - typically overridden
        await self.app(scope, receive, send)

    def _should_check(self, path: str) -> bool:
        """Determine if path should be checked.

        Args:
            path: Request path

        Returns:
            True if path should be checked for mapping consistency
        """
        # Check exclude paths first
        for exclude in self.exclude_paths:
            if path.startswith(exclude):
                return False

        # If protected paths specified, only check those
        if self.protected_paths:
            return any(path.startswith(p) for p in self.protected_paths)

        # Default: check all paths not excluded
        return True


def build_aggregation_blocked_response(
    error: AggregationBlockedError,
) -> JSONResponse:
    """Build JSONResponse for aggregation blocked error.

    This function can be used in exception handlers to build
    consistent error responses.

    Args:
        error: AggregationBlockedError exception

    Returns:
        JSONResponse with structured error
    """
    return JSONResponse(
        status_code=403,
        content={
            "code": error.code.value,
            "message": error.message,
            "details": error.details,
            "retryable": error.retryable,
            "requestId": error.request_id,
        },
    )
