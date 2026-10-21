"""Runs the worker over one crafting app, as its image does: `python -m artifactr.files.worker`.

It reads its settings from the environment: `WORKER_TOKEN`, the token the deployment generated;
`WORKER_APP`, the app by its name, `wordcraft` by default; `WORKER_CLI` and `WORKER_VERSION`, the
app's pinned CLI and the version it must be; `WORKER_BUILD`, the image's digest, if it runs in
one; `WORKER_LIMITS`, the deployment's `Limits` as JSON, any it leaves out the default, and
every one if it is unset or empty; `WORKER_SWEEP`, `1` where the worker is alone in its
container, to kill every other process of its user and empty the temporary directory after each
call; and `WORKER_HOST` and `WORKER_PORT`, where it listens,
127.0.0.1 and 8080 by default. In its container it listens on the internal network alone.

The CLI is started under the limits' launcher, and one that confines nothing runs trusted: the
worker is its confinement (native files ADR-0013).
"""

import os
from collections.abc import Mapping, Sequence
from functools import partial
from types import MappingProxyType
from typing import Final, Protocol

import uvicorn
from starlette.applications import Starlette

from artifactr.files.app import App
from artifactr.files.blender import Subprocess as Blender
from artifactr.files.cadcraft import Subprocess as CadCraft
from artifactr.files.deckcraft import Subprocess as DeckCraft
from artifactr.files.designcraft import Subprocess as DesignCraft
from artifactr.files.figcraft import Subprocess as FigCraft
from artifactr.files.freecad import Subprocess as FreeCad
from artifactr.files.gridcraft import Subprocess as GridCraft
from artifactr.files.pdfcraft import Subprocess as PdfCraft
from artifactr.files.photocraft import Subprocess as PhotoCraft
from artifactr.files.vectorcraft import Subprocess as VectorCraft
from artifactr.files.wordcraft import Subprocess as WordCraft
from artifactr.files.worker.limits import Limits
from artifactr.files.worker.service import worker_app
from artifactr.files.worker.sweep import sweep
from artifactr.files.worker.wire import CALL_LIMIT

HEAD: Final = CALL_LIMIT + (16 << 10)
"""The most bytes the server reads of a request's head: the longest call, and the other headers."""


class Adapter(Protocol):
    """How the worker makes an app: its adapter, given the CLI, its version and the limits."""

    def __call__(self, cli: str, /, *, version: str, limit: int, launcher: Sequence[str]) -> App:
        """Make the app."""
        ...


TOKEN: Final = 32
"""The fewest characters the deployment's token may have: `openssl rand -hex 32` makes 64."""

ADAPTERS: Final[Mapping[str, Adapter]] = MappingProxyType(
    {
        "wordcraft": WordCraft,
        "pdfcraft": PdfCraft,
        "photocraft": PhotoCraft,
        "vectorcraft": VectorCraft,
        "designcraft": DesignCraft,
        # Their CLIs confine nothing: the worker is their confinement.
        "gridcraft": partial(GridCraft, trusted=True),
        "deckcraft": partial(DeckCraft, trusted=True),
        "cadcraft": partial(CadCraft, trusted=True),
        "figcraft": partial(FigCraft, trusted=True),
        "freecad": partial(FreeCad, trusted=True),
        "blender": partial(Blender, trusted=True),
    }
)
"""The apps a worker runs, by name: each app whose files lattice keeps."""


def app_from_environment(environ: Mapping[str, str], limits: Limits) -> App:
    """The app the environment names, its CLI started under the limits.

    Raises:
        ValueError: If it names an app no worker runs.
    """
    name = environ.get("WORKER_APP", "wordcraft")
    if (adapter := ADAPTERS.get(name)) is None:
        raise ValueError(f"WORKER_APP is {name!r}, and a worker runs one of {', '.join(ADAPTERS)}")
    return adapter(
        environ["WORKER_CLI"],
        version=environ["WORKER_VERSION"],
        limit=limits.files,
        launcher=limits.launcher(),
    )


def worker_from_environment(environ: Mapping[str, str]) -> Starlette:
    """The worker the environment's settings describe.

    Raises:
        ValueError: If the token is shorter than `TOKEN`, or the environment still names WordCraft
            the way the worker once read it.
    """
    if "WORKER_CLI" not in environ and "WORDCRAFT_CLI" in environ:
        raise ValueError(
            "WORDCRAFT_CLI and WORDCRAFT_VERSION are now WORKER_CLI and WORKER_VERSION, "
            "with WORKER_APP=wordcraft"
        )
    if 0 < len(environ["WORKER_TOKEN"]) < TOKEN:
        raise ValueError(f"WORKER_TOKEN must be at least {TOKEN} characters, such as a random hex")
    limits = Limits.model_validate_json(environ.get("WORKER_LIMITS") or "{}")
    return worker_app(
        app_from_environment(environ, limits),
        token=environ["WORKER_TOKEN"],
        limits=limits,
        build=environ.get("WORKER_BUILD"),
        sweep=sweep if environ.get("WORKER_SWEEP") == "1" else None,
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
