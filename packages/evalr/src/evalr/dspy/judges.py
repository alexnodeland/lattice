"""DSPy judges: language-model evaluators whose signatures come from their types."""

import hashlib
import json
from contextlib import AbstractContextManager, nullcontext
from enum import Enum

import dspy
from opentelemetry import trace
from pydantic import BaseModel

from evalr.core import (
    FieldKind,
    InputFormatter,
    Verdict,
    get_tracer,
    judging,
    score_type_name,
    verdict_fields,
)
from evalr.dspy.signatures import judge_signature

__all__ = ["DspyJudge", "program_version"]

_EMPTY = frozenset({"", "none", "null"})


class DspyJudge[InputT: BaseModel, VerdictT: BaseModel]:
    """A language-model judge: a DSPy program that reads an input and gives a typed verdict.

    Its signature is derived from the types (``judge_signature``): one text input per field of
    the input type, rendered by a formatter within a token budget, and one output per field of
    the verdict type, with the field's description as its instruction. The output is validated
    as the verdict type, so a bounded rating out of range fails rather than passing through.

    Its version is a hash of its program (instructions, demonstrations, fields) and of the two
    types, so a judge trained with GEPA gets a new version, and verdicts from before and after
    never mix. DSPy reports no per-call cost, so its verdicts' cost is unknown.

    Example:
        ```python
        judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))
        verdict = await judge.evaluate(thread)
        ```
    """

    def __init__(
        self,
        verdict_type: type[VerdictT],
        *,
        inputs: type[InputT],
        name: str | None = None,
        instructions: str | None = None,
        reasoning: bool = False,
        lm: dspy.BaseLM | None = None,
        formatter: InputFormatter | None = None,
        tracer_provider: trace.TracerProvider | None = None,
    ) -> None:
        """Build a judge from its types.

        Args:
            verdict_type: The verdict the judge gives.
            inputs: The input the judge reads.
            name: The judge's name; ``{verdict type}-judge`` in snake case by default.
            instructions: The program's starting instructions; derived from the types by
                default. Training with GEPA rewrites them.
            reasoning: Think step by step before answering (DSPy's ``ChainOfThought``).
            lm: The language model; DSPy's configured one by default.
            formatter: Renders the input within a token budget; ``InputFormatter()`` by default.
            tracer_provider: Where evaluation spans go; the global provider by default.

        Raises:
            UnsupportedField: The verdict type has a field that cannot be judged.
            ValueError: The types share a field name, or use one DSPy reserves.
        """
        signature = judge_signature(inputs, verdict_type, instructions=instructions)
        self._verdict_type = verdict_type
        self._input_type = inputs
        self._program: dspy.Module = (
            dspy.ChainOfThought(signature) if reasoning else dspy.Predict(signature)
        )
        self._name = name or f"{score_type_name(verdict_type)}-judge"
        self._lm = lm
        self._formatter = formatter or InputFormatter()
        self._tracer = get_tracer(tracer_provider)
        self._version = program_version(self._program, inputs, verdict_type)

    @property
    def name(self) -> str:
        """The judge's name."""
        return self._name

    @property
    def version(self) -> str:
        """A hash of the program and the types: 12 hex digits."""
        return self._version

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The verdict type."""
        return self._verdict_type

    @property
    def input_type(self) -> type[InputT]:
        """The input type."""
        return self._input_type

    @property
    def program(self) -> dspy.Module:
        """The DSPy program: a ``Predict``, or a ``ChainOfThought`` with reasoning."""
        return self._program

    @property
    def instructions(self) -> str:
        """The program's current instructions."""
        (_, predictor), *_ = self._program.named_predictors()
        return predictor.signature.instructions

    @property
    def lm(self) -> dspy.BaseLM | None:
        """The language model, if the judge has its own."""
        return self._lm

    def lm_context(self) -> AbstractContextManager[None]:
        """A context in which DSPy uses the judge's language model, if it has its own."""
        return dspy.context(lm=self._lm) if self._lm is not None else nullcontext()

    def inputs(self, input: InputT) -> dict[str, str]:
        """The program's inputs for an input: its fields as text, within the budget."""
        return self._formatter.fields(input)

    async def evaluate(self, input: InputT, /) -> Verdict[VerdictT]:
        """Judge one input.

        Raises:
            pydantic.ValidationError: The model's answer is not a valid verdict.
        """
        with judging(
            self._tracer,
            evaluator=self._name,
            version=self._version,
            verdict_type=self._verdict_type,
        ) as run:
            with self.lm_context():
                prediction = await self._program.acall(**self.inputs(input))
            return run.verdict(self.parse(prediction))

    def parse(self, prediction: dspy.Prediction) -> VerdictT:
        """Validate a prediction's outputs as the verdict type.

        An optional text field the model filled with ``None``, ``null`` or nothing is empty.

        Raises:
            pydantic.ValidationError: The outputs are not a valid verdict.
        """
        values: dict[str, object] = {}
        for field in verdict_fields(self._verdict_type):
            value: object = prediction.get(field.name)
            if (
                field.kind is FieldKind.TEXT
                and field.optional
                and isinstance(value, str)
                and value.strip().lower() in _EMPTY
            ):
                value = None
            values[field.name] = value
        return self._verdict_type.model_validate(values)


def program_version(
    program: dspy.Module, input_type: type[BaseModel], verdict_type: type[BaseModel]
) -> str:
    """Hash a program and the types it judges between: 12 hex digits.

    The hash covers the program's state (instructions, demonstrations, fields) and how every
    field of the types is judged, described in terms that are the same on every Python and
    pydantic version.
    """
    fields: list[dict[str, object]] = [
        {
            "name": f.name,
            "kind": f.kind.value,
            "choices": [c.value if isinstance(c, Enum) else c for c in f.choices],
            "lower": f.lower,
            "upper": f.upper,
            "optional": f.optional,
        }
        for f in verdict_fields(verdict_type)
    ]
    canonical = json.dumps(
        {
            "program": program.dump_state(),
            "inputs": list(input_type.model_fields),
            "verdict": fields,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
