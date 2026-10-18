"""What the forms modules share: how a size is measured, a number, and a refusal.

Private to artifactr.ui: an application measures nothing itself, and portalr repeats the measure
in TypeScript (ADR-0077).
"""

import json
import math
from typing import Annotated, Final

from pydantic import BeforeValidator, JsonValue, ValidationError
from pydantic_core import PydanticCustomError

from artifactr.core import ValidationFailed

MAX_NUMBER: Final = 2**53 - 1
"""The largest number, either way, a form or a dashboard holds: JavaScript's
``Number.MAX_SAFE_INTEGER``, the largest past which two integers read alike, so portalr reads
each as it was written."""


def json_size(value: JsonValue) -> int:
    """Measure a value as the limits do: the UTF-8 bytes of its compact JSON.

    The JSON is written with no spaces after separators, non-ASCII characters as they are, and
    keys in the order the value holds them: as JavaScript's ``JSON.stringify`` writes it.
    """
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def refusal(message: str, error: ValidationError) -> ValidationFailed:
    """Turn Pydantic's errors into a refusal whose message names each one.

    The refusal's ``errors`` are Pydantic's, as artifactr's refusals carry them, each with the
    ``loc`` of what it refuses; its message lists them, so a model that reads only the message
    learns which keyword or property to change.
    """
    errors: list[JsonValue] = json.loads(error.json(include_url=False))
    named = "; ".join(
        f"{'.'.join(str(part) for part in each['loc']) or '(the whole)'}: {each['msg']}"
        for each in error.errors(include_url=False)
    )
    return ValidationFailed(f"{message}: {named}", errors)


def as_number(value: object) -> object:
    """A JSON number within :data:`MAX_NUMBER` either way: never a bool, a string or infinite."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PydanticCustomError("number_type", "Input should be a number")
    if (isinstance(value, float) and not math.isfinite(value)) or abs(value) > MAX_NUMBER:
        raise PydanticCustomError(
            "number_range", "Input should be a number within ±(2**53 - 1)", {"limit": MAX_NUMBER}
        )
    return value


Number = Annotated[int | float, BeforeValidator(as_number)]
"""A number, kept as it was written: ``1`` stays an int and ``1.5`` a float, within
:data:`MAX_NUMBER` either way."""
