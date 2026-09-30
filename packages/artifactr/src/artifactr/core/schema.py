"""The thread protocol's JSON Schema, generated from its frame models.

The schema is checked in at ``schemas/artifactr.v1.json``; a test fails if it drifts from the
models. Regenerate it with ``make schema``, or::

    python -m artifactr.core.schema > schemas/artifactr.v1.json

Clients generate their types from it, for example with ``json-schema-to-typescript``.
"""

import json
import sys
from typing import Any

from pydantic import BaseModel

from artifactr.core.protocol import PROTOCOL, ClientFrame, ServerFrame


class _Frames(BaseModel):
    client: ClientFrame
    server: ServerFrame


def protocol_schema() -> dict[str, Any]:
    """Return the JSON Schema of every frame a client sends and a server sends."""
    frames = _Frames.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": PROTOCOL,
        "description": (
            f"Frames of the {PROTOCOL} thread protocol: `client` is any frame a client sends, "
            "`server` any frame a server sends."
        ),
        "type": "object",
        "properties": frames["properties"],
        "$defs": frames["$defs"],
    }


def main() -> None:
    """Write the schema to standard output."""
    sys.stdout.write(json.dumps(protocol_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
