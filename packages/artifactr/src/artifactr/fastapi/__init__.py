"""The thread protocol over WebSocket, and REST commands and reads, as a FastAPI router.

Include it in an application and give it the host's authentication::

    async def resolve_actor(connection: HTTPConnection) -> tuple[str, Actor]:
        user = await authenticate(connection.headers)  # the application's own auth
        return user.tenant_id, UserActor(id=user.id, name=user.name)


    app.include_router(
        artifactr_router(workspaces, runner, resolve_actor=resolve_actor), prefix="/v1"
    )

Every command, over either transport, goes through :meth:`artifactr.agent.Runner.execute`, so it
behaves identically (ADR-0012). See ``docs/protocol.md`` for the wire format.
"""

from artifactr.fastapi.router import (
    STATUS_CODES,
    Authorize,
    ResolveActor,
    Unauthorized,
    artifactr_router,
)

__all__ = ["STATUS_CODES", "Authorize", "ResolveActor", "Unauthorized", "artifactr_router"]
