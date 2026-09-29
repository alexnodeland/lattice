"""How each field of a verdict type is judged and scored.

A verdict type is any Pydantic model (ADR-0001). The type of each field decides how evaluators
fill it and how it is scored:

- ``bool`` is binary: yes or no.
- ``Literal`` and ``Enum`` are categorical: one of a fixed set of choices.
- ``int`` bounded on both sides is ordinal: a rating on a scale.
- Any other ``int`` or ``float`` is numeric.
- ``str`` is free text. Only language-model judges fill it, and agreement metrics skip it.

``X | None`` is judged as ``X``, and may be left empty. Other types (lists, nested models, unions of
several types) cannot be judged, and raise ``UnsupportedField``.
"""

import types
from dataclasses import dataclass
from enum import Enum, StrEnum
from functools import cache
from typing import Annotated, Literal, Union, cast, get_args, get_origin

import annotated_types
from pydantic import BaseModel, JsonValue
from pydantic.fields import FieldInfo

__all__ = ["FieldKind", "UnsupportedField", "VerdictField", "canonical_fields", "verdict_fields"]


class FieldKind(StrEnum):
    """How a verdict field is judged and scored."""

    BINARY = "binary"
    """A ``bool``: yes or no."""
    CATEGORICAL = "categorical"
    """A ``Literal`` or ``Enum``: one of a fixed set of choices."""
    ORDINAL = "ordinal"
    """An ``int`` bounded on both sides: a rating on a scale."""
    NUMERIC = "numeric"
    """Any other ``int`` or ``float``."""
    TEXT = "text"
    """A ``str``: free text, which only language-model judges fill, and which is not scored."""


class UnsupportedField(TypeError):
    """A verdict field has a type that evaluators cannot judge."""


@dataclass(frozen=True, slots=True)
class VerdictField:
    """One field of a verdict type, as evaluators and metrics see it.

    Attributes:
        name: The field's name on the model.
        kind: How the field is judged and scored.
        description: The field's description, which judges read as an instruction.
        choices: The allowed values of a categorical field, in declaration order: the
            ``Literal``'s arguments or the ``Enum``'s members. ``(False, True)`` for a binary
            field, and empty for other kinds.
        lower: The inclusive lower bound of a numeric or ordinal field, if it has one. An ordinal
            field's exclusive bound is converted (``gt=0`` becomes 1); a float's is kept as is.
        upper: The upper bound, likewise.
        optional: Whether the field accepts ``None``.
        required: Whether the model requires a value for the field.
    """

    name: str
    kind: FieldKind
    description: str | None = None
    choices: tuple[object, ...] = ()
    lower: float | None = None
    upper: float | None = None
    optional: bool = False
    required: bool = True

    @property
    def scored(self) -> bool:
        """Whether agreement metrics score the field: every kind but text."""
        return self.kind is not FieldKind.TEXT


def verdict_fields(verdict_type: type[BaseModel]) -> tuple[VerdictField, ...]:
    """Describe how each field of a verdict type is judged, in declaration order.

    Args:
        verdict_type: Any Pydantic model.

    Returns:
        One ``VerdictField`` per field of the model.

    Raises:
        UnsupportedField: A field's type cannot be judged, such as a list or a nested model.
    """
    return _verdict_fields(verdict_type)


def canonical_fields(verdict_type: type[BaseModel]) -> list[JsonValue]:
    """How each field of a verdict type is judged, as JSON no Python or pydantic upgrade changes.

    Each field is its name, kind, choices (an ``Enum``'s values), bounds and whether it may be
    empty. Evaluators hash it into their versions, so a change to how a field is judged changes
    them.
    """
    return [
        {
            "name": f.name,
            "kind": f.kind.value,
            "choices": [cast(JsonValue, c.value if isinstance(c, Enum) else c) for c in f.choices],
            "lower": f.lower,
            "upper": f.upper,
            "optional": f.optional,
        }
        for f in verdict_fields(verdict_type)
    ]


@cache
def _verdict_fields(verdict_type: type[BaseModel]) -> tuple[VerdictField, ...]:
    return tuple(
        _describe(verdict_type, name, info) for name, info in verdict_type.model_fields.items()
    )


def _describe(verdict_type: type[BaseModel], name: str, info: FieldInfo) -> VerdictField:
    annotation, metadata, optional = _unwrap(info.annotation, list(info.metadata))
    constraints = _constraints(metadata)
    choices: tuple[object, ...] = ()
    lower: float | None = None
    upper: float | None = None
    if annotation is bool:
        kind, choices = FieldKind.BINARY, (False, True)
    elif get_origin(annotation) is Literal:
        kind, choices = FieldKind.CATEGORICAL, get_args(annotation)
    elif isinstance(annotation, type) and issubclass(annotation, Enum):
        kind, choices = FieldKind.CATEGORICAL, tuple(annotation)
    elif annotation is int:
        lower, upper = _bounds(constraints, integer=True)
        both = lower is not None and upper is not None
        kind = FieldKind.ORDINAL if both else FieldKind.NUMERIC
    elif annotation is float:
        kind = FieldKind.NUMERIC
        lower, upper = _bounds(constraints, integer=False)
    elif annotation is str:
        kind = FieldKind.TEXT
    else:
        raise UnsupportedField(
            f"{verdict_type.__name__}.{name}: {info.annotation!r} cannot be judged; verdict "
            "fields are bool, Literal, Enum, int, float or str, optionally with None"
        )
    return VerdictField(
        name=name,
        kind=kind,
        description=info.description or _nested_description(metadata),
        choices=choices,
        lower=lower,
        upper=upper,
        optional=optional,
        required=info.is_required(),
    )


def _unwrap(annotation: object, metadata: list[object]) -> tuple[object, list[object], bool]:
    """Strip ``Annotated`` and ``| None``, collecting metadata from every level."""
    optional = False
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            base, *extra = get_args(annotation)
            metadata = [*metadata, *extra]
            annotation = base
        elif origin is Union or origin is types.UnionType:
            members = [a for a in get_args(annotation) if a is not type(None)]
            if len(members) != 1:
                return annotation, metadata, optional
            optional = True
            annotation = members[0]
        else:
            return annotation, metadata, optional


def _constraints(metadata: list[object]) -> list[object]:
    """Flatten grouped constraints: a nested ``Field`` or an ``Interval``."""
    flat: list[object] = []
    for item in metadata:
        if isinstance(item, FieldInfo):
            flat.extend(_constraints(item.metadata))
        elif isinstance(item, annotated_types.GroupedMetadata):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


def _nested_description(metadata: list[object]) -> str | None:
    for item in metadata:
        if isinstance(item, FieldInfo) and item.description:
            return item.description
    return None


def _bounds(constraints: list[object], *, integer: bool) -> tuple[float | None, float | None]:
    lower: float | None = None
    upper: float | None = None
    step = 1 if integer else 0
    for item in constraints:
        if isinstance(item, annotated_types.Ge):
            lower = _number(item.ge, 0)
        elif isinstance(item, annotated_types.Gt):
            lower = _number(item.gt, step)
        elif isinstance(item, annotated_types.Le):
            upper = _number(item.le, 0)
        elif isinstance(item, annotated_types.Lt):
            upper = _number(item.lt, -step)
    return lower, upper


def _number(bound: object, step: int) -> float | None:
    """A numeric bound as a float, moved by ``step``; ``None`` for a bound that is not a number."""
    return float(bound) + step if isinstance(bound, int | float) else None
