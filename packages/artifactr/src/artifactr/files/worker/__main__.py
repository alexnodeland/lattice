"""Runs the worker over WordCraft, as its image does: `python -m artifactr.files.worker`.

It reads its settings from the environment: `WORKER_TOKEN`, the token the deployment generated;
`WORDCRAFT_CLI` and `WORDCRAFT_VERSION`, the pinned CLI and the version it must be; `WORKER_BUILD`,
the image's digest, if it runs in one; `WORKER_LIMITS`, the deployment's `Limits` as JSON, any it
leaves out the default; and `WORKER_HOST` and `WORKER_PORT`, where it listens, 127.0.0.1 and 8080
by default. In its container it listens on the internal network alone.
"""

import os
from collections.abc import Mapping

import uvicorn
from starlette.applications import Starlette

from artifactr.files.wordcraft import Subprocess
from artifactr.files.worker.limits import Limits
from artifactr.files.worker.service import worker_app
from artifactr.files.worker.wire import CALL_LIMIT


def worker_from_environment(environ: Mapping[str, str]) -> Starlette:
    """The worker the environment's settings describe."""
    limits = Limits.model_validate_json(environ.get("WORKER_LIMITS", "{}"))
    wordcraft = Subprocess(
        environ["WORDCRAFT_CLI"],
        version=environ["WORDCRAFT_VERSION"],
        limit=limits.files,
        launcher=limits.launcher(),
    )
    return worker_app(
        wordcraft, token=environ["WORKER_TOKEN"], limits=limits, build=environ.get("WORKER_BUILD")
    )


def main() -> None:
    """Serve the worker, reading a request's head up to the longest call and its headers."""
    uvicorn.run(
        worker_from_environment(os.environ),
        host=os.environ.get("WORKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("WORKER_PORT", "8080")),
        http="h11",
        h11_max_incomplete_event_size=CALL_LIMIT + (16 << 10),
    )


if __name__ == "__main__":
    main()
