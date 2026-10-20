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
from artifactr.core.questions import Answers, Questions, Reply


class _Frames(BaseModel):
    client: ClientFrame
    server: ServerFrame
    ask_user: Questions
    ask_user_answer: Answers | Reply


def protocol_schema() -> dict[str, Any]:
    """Return the JSON Schema of the frames, and of ``ask_user``'s questions and answers."""
    frames = _Frames.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": PROTOCOL,
        "description": (
            f"Frames of the {PROTOCOL} thread protocol: `client` is any frame a client sends, "
            "`server` any frame a server sends. `ask_user` is the `args` of a paused request "
            "whose `tool_name` is `ask_user`, and `ask_user_answer` the `answer` it takes."
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
