"""Runs the worker over one crafting app, as its image does: `python -m artifactr.files.worker`.

It reads its settings from the environment: `WORKER_TOKEN`, the token the deployment generated;
`WORKER_APP`, the app by its name, `wordcraft` by default; `WORKER_CLI` and `WORKER_VERSION`, the
app's pinned CLI and the version it must be; `WORKER_BUILD`, the image's digest, if it runs in
one; `WORKER_LIMITS`, the deployment's `Limits` as JSON, any it leaves out the default; and
`WORKER_HOST` and `WORKER_PORT`, where it listens, 127.0.0.1 and 8080 by default. In its
container it listens on the internal network alone.

The CLI is started under the limits' launcher, and one that confines nothing runs trusted: the
worker is its confinement (native files ADR-0013).
"""

import os
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

import uvicorn
from starlette.applications import Starlette

from artifactr.files import (
    cadcraft,
    deckcraft,
    designcraft,
    figcraft,
    gridcraft,
    pdfcraft,
    photocraft,
    vectorcraft,
    wordcraft,
)
from artifactr.files.craft import Headless
from artifactr.files.worker.limits import Limits
from artifactr.files.worker.service import worker_app
from artifactr.files.worker.wire import CALL_LIMIT

HEAD: Final = CALL_LIMIT + (16 << 10)
"""The most bytes the server reads of a request's head: the longest call, and the other headers."""


def _by_name(*adapters: type[Headless]) -> Mapping[str, type[Headless]]:
    return MappingProxyType({adapter.craft.name: adapter for adapter in adapters})


ADAPTERS: Final = _by_name(
    wordcraft.Subprocess,
    gridcraft.Subprocess,
    deckcraft.Subprocess,
    pdfcraft.Subprocess,
    cadcraft.Subprocess,
    photocraft.Subprocess,
    vectorcraft.Subprocess,
    designcraft.Subprocess,
    figcraft.Subprocess,
)
"""The apps a worker runs, by name: each crafting app whose files lattice keeps."""


def app_from_environment(environ: Mapping[str, str], limits: Limits) -> Headless:
    """The app the environment names, its CLI started under the limits.

    Raises:
        ValueError: If it names an app no worker runs.
    """
    name = environ.get("WORKER_APP", "wordcraft")
    if (adapter := ADAPTERS.get(name)) is None:
        raise ValueError(f"WORKER_APP is {name!r}, and a worker runs one of {', '.join(ADAPTERS)}")
    cli, version = environ["WORKER_CLI"], environ["WORKER_VERSION"]
    launcher = limits.launcher()
    if adapter.craft.roots == "none":
        return adapter(cli, version=version, trusted=True, limit=limits.files, launcher=launcher)
    return adapter(cli, version=version, limit=limits.files, launcher=launcher)


def worker_from_environment(environ: Mapping[str, str]) -> Starlette:
    """The worker the environment's settings describe."""
    limits = Limits.model_validate_json(environ.get("WORKER_LIMITS", "{}"))
    return worker_app(
        app_from_environment(environ, limits),
        token=environ["WORKER_TOKEN"],
        limits=limits,
        build=environ.get("WORKER_BUILD"),
    )


def main() -> None:
    """Serve the worker, reading a request's head up to the longest call and its headers."""
    uvicorn.run(
        worker_from_environment(os.environ),
        host=os.environ.get("WORKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("WORKER_PORT", "8080")),
        http="h11",
        h11_max_incomplete_event_size=HEAD,
    )


if __name__ == "__main__":
    main()
