"""What a refusal names."""

from typing import Any, cast

from artifactr.core import ValidationFailed


def locs(refusal: ValidationFailed) -> list[Any]:
    """The ``loc`` of each of a refusal's errors, in order."""
    return [cast("dict[str, Any]", error)["loc"] for error in refusal.errors]
