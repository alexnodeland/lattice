"""The wire schema: the JSON Schema of a diagram's data, and the integration that governs it.

The schema is checked in at ``schemas/artifactr_excalidraw.v1.json``; a test fails if it drifts
from the models. portalr generates its TypeScript types from it. Regenerate it with
``moon run artifactr:schema``, or::

    python -m artifactr.excalidraw.wire > schemas/artifactr_excalidraw.v1.json
"""

import json
import sys
from typing import Any

from pydantic import BaseModel

from artifactr.excalidraw.integrations import IntegrationKey
from artifactr.excalidraw.types import Diagram

__all__ = ["wire_schema"]


class _Wire(BaseModel):
    excalidraw_diagram: Diagram
    integration_key: IntegrationKey


def wire_schema() -> dict[str, Any]:
    """Return the JSON Schema of a diagram's data, and of the integration's key."""
    wire = _Wire.model_json_schema(by_alias=True)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "artifactr_excalidraw.v1",
        "description": (
            "`excalidraw_diagram`: the data of a diagram, an Excalidraw scene's elements keyed "
            "by their ids; and `integration_key`: the `integration` a `not_enabled` refusal of "
            "one names."
        ),
        "type": "object",
        "properties": wire["properties"],
        "required": wire["required"],
        "$defs": wire["$defs"],
    }


def main() -> None:
    """Write the wire schema to standard output."""
    sys.stdout.write(json.dumps(wire_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
