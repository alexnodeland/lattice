"""Scores: verdicts and people's feedback as the named values observability backends record.

Every field of a verdict, or of a piece of feedback, becomes one score named ``{type}.{field}``.
The mapping is the one artifactr and reflexr use for feedback, and they build on it (ADR-0011).
A field's kind decides the score's data type (``score_configs``):

- binary fields are ``BOOLEAN``
- ordinal and numeric fields are ``NUMERIC``
- categorical fields are ``CATEGORICAL``, with the choice as a string
- text fields are ``TEXT``

A field left empty (``None`` or ``""``) gives no score, and a category or text longer than
``MAX_TEXT`` characters is cut. A verdict's scores have ids derived from what the verdict is
about, the evaluator and the field, so recording a verdict again replaces its scores rather than
adding more.
"""

import hashlib
import uuid
from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Self, cast

from pydantic import AwareDatetime, BaseModel, Field, JsonValue, model_validator

from evalr.core.fields import ScoreConfig, ScoreDataType, score_configs
from evalr.core.verdicts import Verdict

__all__ = ["MAX_TEXT", "SCORE_NAMESPACE", "Score", "score_values", "scores"]

SCORE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/alexnodeland/evalr/scores")
"""The namespace of the ids ``scores`` gives."""

MAX_TEXT = 500
"""The longest category or text a score holds, in characters; longer ones are cut."""

_VALUE_TYPES: dict[ScoreDataType, type[object]] = {
    "BOOLEAN": bool,
    "NUMERIC": float,  # bool subclasses int, not float, so a bool is never a NUMERIC value
    "CATEGORICAL": str,
    "TEXT": str,
}


class Score(BaseModel, frozen=True):
    """One field of a verdict, or of a piece of people's feedback, as a named value.

    A score is attached to a trace (and, within it, a span) or to a session. evalr's scores come
    from verdicts and name the evaluator; the libraries' feedback mirrors make scores from
    people's feedback, with no evaluator, and describe where it came from in ``source``.

    Attributes:
        id: Derived from what the score is about and its name, so a sink that upserts by id keeps
            one score per field however often it is recorded.
        name: ``{type}.{field}``.
        value: A bool for ``BOOLEAN``, a float for ``NUMERIC``, and a string for ``CATEGORICAL``
            and ``TEXT``; a value of another type is refused.
        data_type: How the value is to be read.
        trace_id: The trace the score is attached to, when there is one.
        span_id: The span within that trace the score judges, as 16 hex digits, when known;
            only with a trace.
        session_id: The session the score is attached to, such as a thread or a causal chain,
            when it is about the session rather than one trace.
        timestamp: When the score was given, with its time zone; when it is recorded, if
            ``None``.
        evaluator: The evaluator that gave the verdict; ``None`` for people's feedback.
        version: The evaluator's version.
        confidence: The evaluator's confidence in the field's value, when it has one.
        source: Where the score came from, beyond an evaluator: the tenant, workspace and person
            that gave a piece of feedback, for example. Its keys cannot be ``evaluator``,
            ``version`` or ``confidence``, which ``metadata`` adds.
    """

    id: str
    name: str
    value: bool | float | str
    data_type: ScoreDataType
    trace_id: str | None = None
    span_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")] | None = None
    session_id: str | None = None
    timestamp: AwareDatetime | None = None
    evaluator: str | None = None
    version: str | None = None
    confidence: float | None = None
    source: Mapping[str, str] = Field(default_factory=dict[str, str])

    @model_validator(mode="after")
    def _fields_agree(self) -> Self:
        value_type = _VALUE_TYPES[self.data_type]
        if not isinstance(self.value, value_type):
            raise ValueError(
                f"a {self.data_type} score's value is a {value_type.__name__}, not {self.value!r}"
            )
        clashing = sorted(self.source.keys() & {"evaluator", "version", "confidence"})
        if clashing:
            raise ValueError(f"source keys that clash with the score's metadata: {clashing}")
        if self.span_id is not None and self.trace_id is None:
            raise ValueError("a score's span is within its trace, so it needs a trace")
        return self

    @property
    def metadata(self) -> dict[str, JsonValue]:
        """The source, then the evaluator, its version and the confidence, as score metadata."""
        metadata: dict[str, JsonValue] = dict(self.source)
        if self.evaluator is not None:
            metadata["evaluator"] = self.evaluator
        if self.version is not None:
            metadata["version"] = self.version
        if self.confidence is not None:
            metadata["confidence"] = self.confidence
        return metadata


def score_values(
    verdict_type: type[BaseModel],
    value: Mapping[str, object],
    *,
    type_name: str | None = None,
) -> list[tuple[ScoreConfig, bool | float | str]]:
    """Pair each field of a validated value that has a value with its config and score value.

    The libraries keep feedback as JSON, so ``value`` may be a model's JSON (an ``Enum`` as its
    value) as well as its fields.

    Args:
        verdict_type: The value's type, which ``score_configs`` reads.
        value: The value's fields, by name, validated as ``verdict_type``.
        type_name: The ``{type}`` in the scores' names; ``score_type_name`` of the type by
            default.

    Returns:
        A bool for each ``BOOLEAN`` score, a float for each ``NUMERIC`` one, and a string, cut at
        ``MAX_TEXT`` characters, for each ``CATEGORICAL`` and ``TEXT`` one, in the order of the
        type's fields. Fields that are ``None``, ``""`` or missing are left out.
    """
    result: list[tuple[ScoreConfig, bool | float | str]] = []
    for config in score_configs(verdict_type, type_name=type_name):
        raw = value.get(config.field)
        if raw is None or raw == "":
            continue
        result.append((config, _value(config.data_type, raw)))
    return result


def scores(
    verdict: Verdict[BaseModel],
    *,
    type_name: str | None = None,
    subject: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> list[Score]:
    """Turn a verdict into one score per field that has a value.

    Args:
        verdict: The verdict.
        type_name: The ``{type}`` in the scores' names; ``score_type_name`` of the verdict type by
            default. Pass a library's registered feedback name where it differs.
        subject: What the verdict is about, such as a run or an example id. It keys the scores'
            ids, so pass it whenever the verdict has no trace.
        trace_id: The trace to attach the scores to; the verdict's own by default.
        span_id: The span the verdict judges, within that trace, when known.

    Returns:
        The scores, in the order of the verdict type's fields, with values as ``score_values``
        gives them.
    """
    value = verdict.value
    trace = trace_id or verdict.trace_id
    key = subject or trace or _content_key(verdict)
    return [
        Score(
            id=str(
                uuid.uuid5(
                    SCORE_NAMESPACE, f"{key}|{verdict.evaluator}|{verdict.version}|{config.name}"
                )
            ),
            name=config.name,
            value=score_value,
            data_type=config.data_type,
            trace_id=trace,
            span_id=span_id,
            evaluator=verdict.evaluator,
            version=verdict.version,
            confidence=verdict.confidence.get(config.field),
        )
        for config, score_value in score_values(type(value), dict(value), type_name=type_name)
    ]


def _value(data_type: ScoreDataType, raw: object) -> bool | float | str:
    match data_type:
        case "BOOLEAN":
            return bool(raw)
        case "NUMERIC":
            return float(cast(float, raw))
        case _:
            return str(raw.value if isinstance(raw, Enum) else raw)[:MAX_TEXT]


def _content_key(verdict: Verdict[BaseModel]) -> str:
    return hashlib.sha256(verdict.value.model_dump_json().encode()).hexdigest()
