"""Scores: verdicts as the named values observability backends record.

Every field of a verdict becomes one score, named ``{type}.{field}``, the convention artifactr and
reflexr share for feedback. A field's kind decides the score's data type:

- binary fields are ``BOOLEAN``
- ordinal and numeric fields are ``NUMERIC``
- categorical fields are ``CATEGORICAL``, with the choice as a string
- text fields are ``TEXT``

A field left empty (``None``) gives no score. A score's id is derived from what it is about, the
evaluator and the field, so recording a verdict again replaces its scores rather than adding
more.
"""

import hashlib
import re
import uuid
from enum import Enum
from typing import Literal, cast

from pydantic import BaseModel, JsonValue

from evalr.core.fields import FieldKind, verdict_fields
from evalr.core.verdicts import Verdict

__all__ = ["SCORE_NAMESPACE", "Score", "ScoreType", "score_type_name", "scores"]

type ScoreType = Literal["NUMERIC", "BOOLEAN", "CATEGORICAL", "TEXT"]
"""A score's data type, as Langfuse and the OpenTelemetry conventions name them."""

SCORE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/alexnodeland/evalr/scores")
"""The namespace of score ids."""

_DATA_TYPES: dict[FieldKind, ScoreType] = {
    FieldKind.BINARY: "BOOLEAN",
    FieldKind.CATEGORICAL: "CATEGORICAL",
    FieldKind.ORDINAL: "NUMERIC",
    FieldKind.NUMERIC: "NUMERIC",
    FieldKind.TEXT: "TEXT",
}


class Score(BaseModel, frozen=True):
    """One field of one verdict, as a named value.

    Attributes:
        id: Derived from the subject, the evaluator and the name, so a store that upserts by id
            keeps one score per field however often it is recorded.
        name: ``{type}.{field}``.
        value: A bool for ``BOOLEAN``, a float for ``NUMERIC``, and a string for ``CATEGORICAL``
            and ``TEXT``.
        data_type: How the value is to be read.
        trace_id: The trace the score is attached to, when there is one.
        evaluator: The evaluator that gave the verdict.
        version: The evaluator's version.
        confidence: The evaluator's confidence in the field's value, when it has one.
    """

    id: str
    name: str
    value: bool | float | str
    data_type: ScoreType
    trace_id: str | None = None
    evaluator: str
    version: str
    confidence: float | None = None

    @property
    def metadata(self) -> dict[str, JsonValue]:
        """The evaluator, its version and the confidence, as score metadata."""
        metadata: dict[str, JsonValue] = {"evaluator": self.evaluator, "version": self.version}
        if self.confidence is not None:
            metadata["confidence"] = self.confidence
        return metadata


def score_type_name(verdict_type: type[BaseModel]) -> str:
    """The name scores give a verdict type: its class name in snake case.

    ``Helpfulness`` is ``helpfulness`` and ``TaskCompletion`` is ``task_completion``, as the
    libraries name their feedback types by default.
    """
    return re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", verdict_type.__name__
    ).lower()


def scores(
    verdict: Verdict[BaseModel],
    *,
    type_name: str | None = None,
    subject: str | None = None,
    trace_id: str | None = None,
) -> list[Score]:
    """Turn a verdict into one score per field that has a value.

    Args:
        verdict: The verdict.
        type_name: The ``{type}`` in the scores' names; ``score_type_name`` of the verdict type by
            default. Pass a library's registered feedback name where it differs.
        subject: What the verdict is about, such as a run or an example id. It keys the scores'
            ids, so pass it whenever the verdict has no trace.
        trace_id: The trace to attach the scores to; the verdict's own by default.

    Returns:
        The scores, in the order of the verdict type's fields.
    """
    value = verdict.value
    prefix = type_name or score_type_name(type(value))
    trace = trace_id or verdict.trace_id
    key = subject or trace or _content_key(verdict)
    result: list[Score] = []
    for field in verdict_fields(type(value)):
        raw: object = getattr(value, field.name)
        if raw is None:
            continue
        name = f"{prefix}.{field.name}"
        result.append(
            Score(
                id=str(
                    uuid.uuid5(
                        SCORE_NAMESPACE, f"{key}|{verdict.evaluator}|{verdict.version}|{name}"
                    )
                ),
                name=name,
                value=_value(field.kind, raw),
                data_type=_DATA_TYPES[field.kind],
                trace_id=trace,
                evaluator=verdict.evaluator,
                version=verdict.version,
                confidence=verdict.confidence.get(field.name),
            )
        )
    return result


def _value(kind: FieldKind, raw: object) -> bool | float | str:
    match kind:
        case FieldKind.BINARY:
            return bool(raw)
        case FieldKind.ORDINAL | FieldKind.NUMERIC:
            return float(cast(float, raw))
        case _:
            return str(raw.value if isinstance(raw, Enum) else raw)


def _content_key(verdict: Verdict[BaseModel]) -> str:
    return hashlib.sha256(verdict.value.model_dump_json().encode()).hexdigest()
