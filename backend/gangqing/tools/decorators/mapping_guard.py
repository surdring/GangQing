"""Tool decorator for mapping consistency guard.

This module provides decorators that automatically enforce mapping
consistency checks before executing tools that perform cross-system
aggregation.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import structlog

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.semantic.aggregation_gate import (
    AggregationBlockedError,
    AggregationGate,
    AggregationGateResult,
    EntityRef,
    MappingVersionManagerProtocol,
)
from gangqing.semantic.mapping_versioning import MappingVersionManager
from gangqing.semantic.models import EntityType


logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class MappingGuardError(AppError):
    """Error raised by mapping guard decorator when check fails.

    This wraps the AggregationBlockedError with additional tool context.
    """

    def __init__(
        self,
        tool_name: str,
        blocked_error: AggregationBlockedError,
        *,
        request_id: str,
    ) -> None:
        """Initialize mapping guard error.

        Args:
            tool_name: Name of the tool being guarded
            blocked_error: The underlying aggregation blocked error
            request_id: Request ID for tracing
        """
        message = (
            f"Tool '{tool_name}' execution blocked: {blocked_error.message}"
        )

        details = {
            "tool_name": tool_name,
            "underlying_error": blocked_error.to_response().dict(),
        }

        super().__init__(
            code=ErrorCode.AGGREGATION_BLOCKED,
            message=message,
            request_id=request_id,
            details=details,
            retryable=False,
        )
        self.tool_name = tool_name
        self.blocked_error = blocked_error


def require_mapping_consistency(
    entity_refs_extractor: Callable[..., List[EntityRef]],
    *,
    fail_silent: bool = False,
    log_on_block: bool = True,
) -> Callable[[F], F]:
    """Decorator factory for requiring mapping consistency.

    This decorator automatically:
    1. Extracts entity references from tool parameters
    2. Runs aggregation gate check
    3. Raises MappingGuardError if mapping conflicts detected

    Usage:
        @require_mapping_consistency(
            entity_refs_extractor=lambda ctx, params: [
                EntityRef(
                    unified_id=params["equipment_id"],
                    entity_type=EntityType.EQUIPMENT,
                    required_source_systems=["ERP", "MES", "DCS"],
                )
            ]
        )
        def query_equipment_cost(
            ctx: RequestContext,
            params: QueryEquipmentCostParams,
        ) -> ToolResult:
            # This will only execute if mapping is valid
            ...

    Args:
        entity_refs_extractor: Callable that extracts List[EntityRef] from
                              the decorated function's arguments
        fail_silent: If True, returns None/empty result instead of raising
        log_on_block: Whether to log when aggregation is blocked

    Returns:
        Decorator function
    """
    def decorator(func: F) -> F:
        """The actual decorator."""
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper that performs mapping check before executing function."""
            # Extract RequestContext from arguments
            ctx = _extract_request_context(args, kwargs)
            if ctx is None:
                raise ValueError(
                    f"Could not extract RequestContext from {func.__name__} arguments. "
                    "First positional argument or 'ctx' keyword argument must be RequestContext."
                )

            # Extract entity refs using provided extractor
            try:
                entity_refs = entity_refs_extractor(*args, **kwargs)
            except Exception as e:
                logger.error(
                    "entity_refs_extraction_failed",
                    tool=func.__name__,
                    error=str(e),
                    request_id=ctx.request_id,
                )
                raise AppError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Failed to extract entity references: {e}",
                    request_id=ctx.request_id,
                    details={"tool": func.__name__, "error": str(e)},
                    retryable=False,
                ) from e

            # Skip check if no refs
            if not entity_refs:
                return func(*args, **kwargs)

            # Create mapping manager and aggregation gate
            manager = MappingVersionManager(ctx)
            gate = AggregationGate(ctx, manager)

            # Run aggregation gate check
            result = gate.check_aggregation_prerequisites(entity_refs)

            if result.is_blocked:
                # Build the blocked error
                blocked_error = AggregationBlockedError(
                    entity_refs=entity_refs,
                    conflicts=result.conflicts,
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                )

                if log_on_block:
                    logger.warning(
                        "tool_execution_blocked_by_mapping_guard",
                        tool=func.__name__,
                        entity_count=len(entity_refs),
                        conflict_count=len(result.conflicts),
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                    )

                if fail_silent:
                    # Return empty result with warning
                    return _build_blocked_result(result, ctx)

                # Raise mapping guard error
                raise MappingGuardError(
                    tool_name=func.__name__,
                    blocked_error=blocked_error,
                    request_id=ctx.request_id,
                )

            # All checks passed, execute the function
            return func(*args, **kwargs)

        # Attach gate metadata to wrapper for introspection
        wrapper._mapping_guard = {  # type: ignore[attr-defined]
            "entity_refs_extractor": entity_refs_extractor,
            "fail_silent": fail_silent,
        }

        return wrapper  # type: ignore[return-value]

    return decorator


def require_single_entity_mapping(
    unified_id_param: str = "unified_id",
    entity_type_param: str = "entity_type",
    required_source_systems: Optional[List[str]] = None,
    *,
    fail_silent: bool = False,
    log_on_block: bool = True,
) -> Callable[[F], F]:
    """Decorator factory for requiring single entity mapping.

    Simplified version of require_mapping_consistency for tools that
    only work with a single entity.

    Usage:
        @require_single_entity_mapping(
            unified_id_param="equipment_id",
            entity_type_param="entity_type",
            required_source_systems=["ERP", "MES"],
        )
        def get_equipment_status(
            ctx: RequestContext,
            equipment_id: str,
            entity_type: EntityType,
        ) -> ToolResult:
            ...

    Args:
        unified_id_param: Parameter name containing unified_id
        entity_type_param: Parameter name containing entity_type
        required_source_systems: Optional required source systems
        fail_silent: If True, returns None/empty result instead of raising
        log_on_block: Whether to log when aggregation is blocked

    Returns:
        Decorator function
    """
    def extractor(*args: Any, **kwargs: Any) -> List[EntityRef]:
        """Extract single entity reference from arguments."""
        # Try to extract from kwargs first
        unified_id = kwargs.get(unified_id_param)
        entity_type = kwargs.get(entity_type_param)

        # If not in kwargs, try to extract from args using signature
        if unified_id is None or entity_type is None:
            sig = inspect.signature(extractor._wrapped_function)  # type: ignore[attr-defined]
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            unified_id = bound.arguments.get(unified_id_param)
            entity_type = bound.arguments.get(entity_type_param)

        if unified_id is None:
            raise ValueError(f"Parameter '{unified_id_param}' not found in arguments")

        if entity_type is None:
            raise ValueError(f"Parameter '{entity_type_param}' not found in arguments")

        # Ensure entity_type is EntityType enum
        if isinstance(entity_type, str):
            entity_type = EntityType(entity_type)

        return [
            EntityRef(
                unified_id=unified_id,
                entity_type=entity_type,
                required_source_systems=required_source_systems,
            )
        ]

    def decorator(func: F) -> F:
        """The actual decorator."""
        # Store reference for extractor
        extractor._wrapped_function = func  # type: ignore[attr-defined]

        decorated = require_mapping_consistency(
            entity_refs_extractor=extractor,
            fail_silent=fail_silent,
            log_on_block=log_on_block,
        )(func)

        # Update metadata
        decorated._mapping_guard = {  # type: ignore[attr-defined]
            "unified_id_param": unified_id_param,
            "entity_type_param": entity_type_param,
            "required_source_systems": required_source_systems,
        }

        return decorated  # type: ignore[return-value]

    return decorator


def require_entity_list_mapping(
    entity_list_param: str = "entities",
    unified_id_key: str = "unified_id",
    entity_type_key: str = "entity_type",
    *,
    fail_silent: bool = False,
    log_on_block: bool = True,
) -> Callable[[F], F]:
    """Decorator factory for requiring mapping for list of entities.

    For tools that process lists of entities, this decorator extracts
    each entity's unified_id and entity_type from the list.

    Usage:
        @require_entity_list_mapping(
            entity_list_param="equipment_ids",
            unified_id_key="id",
            entity_type_key="type",
        )
        def batch_query_equipment(
            ctx: RequestContext,
            equipment_ids: List[Dict[str, str]],  # [{"id": "E1", "type": "equipment"}]
        ) -> ToolResult:
            ...

    Args:
        entity_list_param: Parameter name containing list of entities
        unified_id_key: Key in entity dict containing unified_id
        entity_type_key: Key in entity dict containing entity_type
        fail_silent: If True, returns None/empty result instead of raising
        log_on_block: Whether to log when aggregation is blocked

    Returns:
        Decorator function
    """
    def extractor(*args: Any, **kwargs: Any) -> List[EntityRef]:
        """Extract entity references from list."""
        entity_list = kwargs.get(entity_list_param)

        if entity_list is None:
            sig = inspect.signature(extractor._wrapped_function)  # type: ignore[attr-defined]
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            entity_list = bound.arguments.get(entity_list_param)

        if entity_list is None:
            raise ValueError(f"Parameter '{entity_list_param}' not found in arguments")

        if not isinstance(entity_list, list):
            raise ValueError(f"Parameter '{entity_list_param}' must be a list")

        refs: List[EntityRef] = []
        for entity in entity_list:
            if isinstance(entity, dict):
                unified_id = entity.get(unified_id_key)
                entity_type_str = entity.get(entity_type_key, "equipment")
                entity_type = EntityType(entity_type_str) if isinstance(entity_type_str, str) else entity_type_str
            else:
                unified_id = str(entity)
                entity_type = EntityType.EQUIPMENT

            if unified_id:
                refs.append(EntityRef(
                    unified_id=unified_id,
                    entity_type=entity_type,
                ))

        return refs

    def decorator(func: F) -> F:
        """The actual decorator."""
        extractor._wrapped_function = func  # type: ignore[attr-defined]

        decorated = require_mapping_consistency(
            entity_refs_extractor=extractor,
            fail_silent=fail_silent,
            log_on_block=log_on_block,
        )(func)

        decorated._mapping_guard = {  # type: ignore[attr-defined]
            "entity_list_param": entity_list_param,
            "unified_id_key": unified_id_key,
            "entity_type_key": entity_type_key,
        }

        return decorated  # type: ignore[return-value]

    return decorator


def _extract_request_context(
    args: tuple,
    kwargs: dict,
) -> Optional[RequestContext]:
    """Extract RequestContext from function arguments.

    Args:
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        RequestContext if found, None otherwise
    """
    # Check kwargs first
    if "ctx" in kwargs and isinstance(kwargs["ctx"], RequestContext):
        return kwargs["ctx"]

    if "context" in kwargs and isinstance(kwargs["context"], RequestContext):
        return kwargs["context"]

    # Check first positional argument
    if args and isinstance(args[0], RequestContext):
        return args[0]

    # Check all positional arguments
    for arg in args:
        if isinstance(arg, RequestContext):
            return arg

    return None


def _build_blocked_result(
    result: AggregationGateResult,
    ctx: RequestContext,
) -> Dict[str, Any]:
    """Build a result object for silent failure mode.

    Args:
        result: Aggregation gate result
        ctx: RequestContext

    Returns:
        Dictionary with error information and empty data
    """
    return {
        "data": None,
        "error": {
            "code": ErrorCode.AGGREGATION_BLOCKED.value,
            "message": result.blocked_reason,
            "details": result.to_dict(),
            "requestId": ctx.request_id,
        },
        "blocked": True,
    }
