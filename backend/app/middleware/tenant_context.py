"""
Tenant context middleware.

Injects tenant_id into request state for endpoints that have resolved
team context (from API key or session). Used for audit and validation.
"""

from typing import Optional
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Injects tenant context into request state.
    Does NOT resolve auth - that is done by route dependencies.
    This middleware only stores tenant_id when already resolved.
    """

    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = getattr(request.state, "tenant_id", None)
        return await call_next(request)


def get_request_tenant_id(request: Request) -> Optional[UUID]:
    """Get tenant_id from request state if set."""
    return getattr(request.state, "tenant_id", None)


def set_request_tenant_id(request: Request, tenant_id: UUID) -> None:
    """Set tenant_id on request state."""
    request.state.tenant_id = tenant_id
