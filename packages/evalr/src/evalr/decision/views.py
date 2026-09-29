"""The decision-only view of a verdict type: the fields a decision model can fill.

A decision model answers typed questions (yes or no, a choice, a score), not free text, and
pydantic-ai asks one per field of the output type. It accepts only some field types, so a
decision evaluator's output type is a view of the verdict type (ADR-0008):

| Verdict field | In the view |
|---|---|
| ``bool``, required | ``bool``: a yes-or-no question |
| ``Literal`` or ``Enum`` of two or more strings or whole numbers | unchanged: a choice |
| ``int`` bounded on both sides (an ordinal), up to 255 values | ``Literal`` of every value |
| ``float`` from 0 to an upper bound, required | unchanged: a yes-or-no question, scaled |
| text, other numbers, optional ``bool`` or ``float`` | left out |

A field left out keeps its default in the verdict, so it must have one.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, Field, create_model

from evalr.core import FieldKind, UnsupportedField, VerdictField, verdict_fields

__all__ = ["MAX_CHOICES", "DecisionView", "decision_view"]

MAX_CHOICES = 255
"""The most options a decision model's choice question offers."""

# Literal, for building one from values known only at run time.
_LITERAL: Any = Literal


@dataclass(frozen=True, slots=True)
class DecisionView:
    """A verdict type as a decision model sees it.

    Attributes:
        model: The output type the decision model fills, named ``{Verdict}Decision``, with the
            verdict type's docstring (the decision's goal) and the fields' descriptions.
        decided: The verdict fields the view has, in order.
        left_out: The verdict fields it leaves out, which keep their defaults.
    """

    model: type[BaseModel]
    decided: tuple[str, ...]
    left_out: tuple[str, ...]


def decision_view(verdict_type: type[BaseModel]) -> DecisionView:
    """Derive the fields of a verdict type that a decision model can fill.

    Raises:
        UnsupportedField: A field the view leaves out has no default, so no verdict could be
            made; give it a default, or judge the type with a language model.
    """
    fields: dict[str, Any] = {}
    left_out: list[str] = []
    for field in verdict_fields(verdict_type):
        info = verdict_type.model_fields[field.name]
        annotation = _annotation(field, info.annotation)
        if annotation is None:
            if field.required:
                raise UnsupportedField(
                    f"{verdict_type.__name__}.{field.name}: a decision model cannot fill this "
                    "field, and it has no default; give it one, or judge the type with a "
                    "language model (evalr.core.Fallback composes the two)"
                )
            left_out.append(field.name)
            continue
        default = info.get_default(call_default_factory=True) if not field.required else ...
        fields[field.name] = (annotation, Field(default, description=field.description))
    model = create_model(f"{verdict_type.__name__}Decision", __doc__=verdict_type.__doc__, **fields)
    return DecisionView(model=model, decided=tuple(fields), left_out=tuple(left_out))


def _annotation(field: VerdictField, annotation: object) -> object | None:
    """The field's type in the view, or ``None`` to leave it out."""
    match field.kind:
        case FieldKind.BINARY if not field.optional:
            return bool
        case FieldKind.CATEGORICAL if _choosable(field.choices):
            return annotation
        case FieldKind.ORDINAL:
            return _scale(field)
        case FieldKind.NUMERIC if _unit_scaled(field):
            return Annotated[float, Field(ge=0, le=field.upper)]
        case _:
            return None


def _unit_scaled(field: VerdictField) -> bool:
    """A required number from 0 up to a bound: a yes-or-no probability, scaled."""
    return field.lower == 0 and field.upper is not None and field.upper > 0 and not field.optional


def _choosable(choices: tuple[object, ...]) -> bool:
    values = [c.value if isinstance(c, Enum) else c for c in choices]
    strings = all(isinstance(v, str) for v in values)
    wholes = all(isinstance(v, int) and not isinstance(v, bool) for v in values)
    return 2 <= len(values) <= MAX_CHOICES and (strings or wholes)


def _scale(field: VerdictField) -> object | None:
    lower, upper = int(cast(float, field.lower)), int(cast(float, field.upper))
    if not 2 <= upper - lower + 1 <= MAX_CHOICES:
        return None
    scale: Any = _LITERAL[tuple(range(lower, upper + 1))]
    return scale | None if field.optional else scale
