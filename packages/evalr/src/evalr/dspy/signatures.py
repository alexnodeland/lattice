"""DSPy signatures derived from an input type and a verdict type.

The signature has one input field per field of the input type, which the judge receives as text
from a formatter, and one output field per field of the verdict type, typed as the field is. Each
field's description becomes the field's instruction, with its bounds spelled out, since DSPy
only reads the type.
"""

import inspect

import dspy
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from evalr.core import FieldKind, VerdictField, verdict_fields

__all__ = ["default_instructions", "judge_signature"]

RESERVED = frozenset({"reasoning"})
"""Field names DSPy's modules use for themselves: chain of thought adds ``reasoning``."""


def default_instructions(input_type: type[BaseModel], verdict_type: type[BaseModel]) -> str:
    """The instructions a judge starts from: what to read, and what to give.

    The verdict type's docstring, when it has one, says what the verdict is for.
    """
    text = f"Read the {input_type.__name__} and judge it, giving a {verdict_type.__name__}."
    doc = verdict_type.__doc__
    return f"{text}\n\n{inspect.cleandoc(doc)}" if doc else text


def judge_signature(
    input_type: type[BaseModel],
    verdict_type: type[BaseModel],
    *,
    instructions: str | None = None,
) -> type[dspy.Signature]:
    """Derive a DSPy signature from an input type and a verdict type.

    Args:
        input_type: The model the judge reads. Each field becomes a text input.
        verdict_type: The model the judge gives. Each field becomes an output of its type.
        instructions: The signature's instructions; ``default_instructions`` by default.

    Raises:
        UnsupportedField: The verdict type has a field that cannot be judged.
        ValueError: The two types share a field name, or use one DSPy reserves.
    """
    outputs = verdict_fields(verdict_type)
    inputs = input_type.model_fields
    names = [*inputs, *(f.name for f in outputs)]
    shared = sorted({n for n in names if names.count(n) > 1 or n in RESERVED})
    if shared:
        raise ValueError(
            f"{input_type.__name__} and {verdict_type.__name__} cannot use the field names "
            f"{shared}: each field of a signature needs its own name, and DSPy reserves "
            f"{sorted(RESERVED)}"
        )
    fields: dict[str, tuple[object, FieldInfo]] = {}
    for name, info in inputs.items():
        fields[name] = (str, dspy.InputField(desc=info.description or name.replace("_", " ")))
    for field in outputs:
        annotation = verdict_type.model_fields[field.name].annotation
        fields[field.name] = (annotation, dspy.OutputField(desc=describe(field)))
    return dspy.make_signature(
        fields, instructions or default_instructions(input_type, verdict_type)
    )


def describe(field: VerdictField) -> str:
    """A verdict field's instruction: its description, its bounds, and whether it may be empty."""
    text = field.description or field.name.replace("_", " ")
    hints: list[str] = []
    if field.kind is FieldKind.ORDINAL:
        hints.append(f"a whole number from {field.lower:g} to {field.upper:g}")
    elif field.kind is FieldKind.NUMERIC and (bounds := _bounds(field)):
        hints.append(bounds)
    if field.optional:
        hints.append("may be left empty")
    return f"{text} ({'; '.join(hints)})" if hints else text


def _bounds(field: VerdictField) -> str | None:
    if field.lower is not None and field.upper is not None:
        return f"a number from {field.lower:g} to {field.upper:g}"
    if field.lower is not None:
        return f"a number of at least {field.lower:g}"
    if field.upper is not None:
        return f"a number of at most {field.upper:g}"
    return None
