"""The application's side of the worker: an `App` that sends every call to it."""

from collections.abc import Sequence
from typing import Final, Self

import httpx
from pydantic import BaseModel, TypeAdapter

from artifactr.files.app import AppCommand, AppFailed, Applied, CommandSpec, Inspection, Talk
from artifactr.files.worker.wire import (
    CALL,
    AppliedReply,
    ApplyCall,
    CommandsCall,
    Failed,
    Hello,
    InspectCall,
    RenderCall,
)

GRACE: Final = 5.0
"""The seconds a reply may take past its call's deadline, for the worker to say how it failed."""

LOOKUP: Final = 30.0
"""The seconds a lookup's reply is waited for, which the worker gives no deadline of its caller's:
an edit's longest by default."""

_SPECS = TypeAdapter(list[CommandSpec])


class Worker:
    """An [`App`][artifactr.files.app.App] that the worker runs: every call is a request to it.

    Made by [`connect`][artifactr.files.worker.Worker.connect], which asks the worker which app
    it runs; its name, version and image's digest are the worker's, and provenance records them.
    A failure the worker reports is raised as the same [`AppFailed`][artifactr.files.app.AppFailed];
    a worker that can't be reached, or doesn't reply in time, is `crashed` or `timeout`.
    """

    def __init__(self, client: httpx.AsyncClient, hello: Hello) -> None:
        self._client = client
        self._hello = hello

    @classmethod
    async def connect(
        cls, url: str, *, token: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> Self:
        """Ask the worker at `url` which app it runs, and return the app.

        Args:
            url: The worker's base URL, on the deployment's internal network.
            token: The token the deployment generated for it.
            transport: How requests are sent, for tests; HTTP by default.

        Raises:
            httpx.HTTPError: If the worker can't be reached, or refuses the token.
        """
        client = httpx.AsyncClient(
            base_url=url, headers={"Authorization": f"Bearer {token}"}, transport=transport
        )
        reply = await client.get("/", timeout=GRACE)
        reply.raise_for_status()
        return cls(client, Hello.model_validate_json(reply.content))

    async def aclose(self) -> None:
        """Close the connections to the worker."""
        await self._client.aclose()

    @property
    def name(self) -> str:
        """The app's name, which provenance records."""
        return self._hello.name

    @property
    def version(self) -> str:
        """The app's version, which provenance records."""
        return self._hello.version

    @property
    def build(self) -> str | None:
        """The digest of the worker's image, which provenance records."""
        return self._hello.build

    @property
    def talk(self) -> Talk:
        """How much the app talks to the host while a person edits in it."""
        return self._hello.talk

    @property
    def integration(self) -> str:
        """The key that switches the app in a workspace."""
        return self._hello.integration

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Apply a batch of commands to a file, or to a new one if `source` is None."""
        call = ApplyCall(deadline=deadline, commands=list(commands))
        reply = await self._send("/apply", call, source or b"", deadline)
        applied = AppliedReply.model_validate_json(reply)
        return Applied(content=applied.content, inspection=applied.inspection)

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a file's fingerprint, outline, text, review and pages."""
        reply = await self._send("/inspect", InspectCall(deadline=deadline), source, deadline)
        return Inspection.model_validate_json(reply)

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Render one page of a file, from 1, as a PNG."""
        call = RenderCall(deadline=deadline, page=page, scale=scale)
        return await self._send("/render", call, source, deadline)

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """Find the commands that match a query, ten at most."""
        reply = await self._send("/commands", CommandsCall(query=query), b"", LOOKUP)
        return _SPECS.validate_json(reply)

    async def _send(self, path: str, call: BaseModel, body: bytes, deadline: float) -> bytes:
        """Send one call, and return its reply's body, or raise how it failed."""
        try:
            reply = await self._client.post(
                path,
                content=body,
                headers={CALL: call.model_dump_json()},
                timeout=deadline + GRACE,
            )
        except httpx.TimeoutException:
            raise AppFailed("timeout", f"the worker didn't reply to {path}") from None
        except httpx.TransportError as error:
            raise AppFailed("crashed", f"the worker can't be reached: {error!r}") from None
        if reply.status_code == 422:
            failed = Failed.model_validate_json(reply.content)
            raise AppFailed(failed.failure, failed.message)
        reply.raise_for_status()
        return reply.content
