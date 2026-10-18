"""The wire schema: the JSON Schema of artifactr.ui's kinds, ``ask_form``'s request and refusals.

The schema is checked in at ``schemas/artifactr_ui.v1.json``; a test fails if it drifts from the
models. portalr generates its TypeScript types from it. Regenerate it with
``moon run artifactr:schema``, or::

    python -m artifactr.ui.wire > schemas/artifactr_ui.v1.json

No other module imports this one, so running it registers the artifact types once.
"""

import json
import sys
from typing import Any

from pydantic import BaseModel

from artifactr.ui.checks import RefusalReason
from artifactr.ui.integrations import IntegrationKey
from artifactr.ui.types import App, Dashboard, Form, FormRequest, Submission

__all__ = ["wire_schema"]


class _Wire(BaseModel):
    form: Form
    submission: Submission
    dashboard: Dashboard
    app: App
    ask_form: FormRequest
    refusal_reason: RefusalReason
    integration_key: IntegrationKey


def wire_schema() -> dict[str, Any]:
    """Return the JSON Schema of each kind's data, and of ``ask_form``'s request's ``args``."""
    wire = _Wire.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "artifactr.ui.v1",
        "description": (
            "The data of artifactr.ui's artifact kinds, by kind; `ask_form`: the `args` of "
            "a paused request whose `tool_name` is `ask_form`; and `refusal_reason`: the "
            "`reason` an `invalid_state` refusal of a submission carries; and "
            "`integration_key`: the `integration` a `not_enabled` refusal names, for the "
            "forms' integrations."
        ),
        "type": "object",
        "properties": wire["properties"],
        "$defs": wire["$defs"],
    }


def main() -> None:
    """Write the wire schema to standard output."""
    sys.stdout.write(json.dumps(wire_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
