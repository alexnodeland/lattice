"""grantr's admin API, as a FastAPI router.

Mount it at ``/grantr/v1`` and give it the application's authentication::

    async def resolve_actor(connection: HTTPConnection) -> Caller:
        if key := connection.headers.get("X-Api-Key"):
            if (found := await grants.authenticate(key)) is None:
                raise Unauthorized("unknown key")
            tenant, principal = found
            return Caller(principal, tenant)
        user = await verify_token(connection.headers)  # the application's own sign-in
        return Caller(User(id=user.sub))


    app.include_router(grantr_router(grants, resolve_actor=resolve_actor), prefix="/grantr/v1")

A refusal keeps the libraries' shape, ``{"type": ..., "message": ...}``: 401 ``unauthorized``
without a caller, 403 ``forbidden``, 422 ``invalid``, and 400 ``tenant_required`` when a caller
in several tenants names none. FastAPI's own 422 for a malformed request keeps its list.
"""

from grantr.fastapi.router import (
    STATUS_CODES,
    Caller,
    ResolveActor,
    Unauthorized,
    grantr_router,
)

__all__ = ["STATUS_CODES", "Caller", "ResolveActor", "Unauthorized", "grantr_router"]
