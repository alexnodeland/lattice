"""DSPy judges: language-model evaluators whose signatures come from their types."""

import copy
import hashlib
import json
import os
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from importlib.metadata import version as _distribution_version
from pathlib import Path
from typing import Any, Self, cast

import dspy
from opentelemetry import trace
from pydantic import BaseModel, JsonValue

from evalr.core import (
    Example,
    FieldKind,
    InputFormatter,
    Training,
    Verdict,
    canonical_fields,
    get_tracer,
    judging,
    score_type_name,
    verdict_fields,
)
from evalr.dspy.signatures import judge_signature

__all__ = ["FORMAT", "DspyJudge", "JudgeMismatch", "SavedJudge", "program_version"]

FORMAT = "evalr.dspy.judge/1"
"""The format of a saved judge (ADR-0007)."""

_EMPTY = frozenset({"", "none", "null"})


class JudgeMismatch(ValueError):
    """A saved judge does not match the types it is loaded with, or is not a judge at all."""


class SavedJudge(BaseModel, frozen=True):
    """A trained judge as JSON: its program, its types' names, and how it was trained.

    Attributes:
        format: ``evalr.dspy.judge/1``.
        name: The judge's name.
        version: A hash of the program and the types.
        input_type: The input type's name.
        verdict_type: The verdict type's name.
        reasoning: Whether the program thinks step by step.
        program: DSPy's JSON state of the program, without any language model.
        training: How it was trained, if it was.
        dependencies: The DSPy and evalr versions that saved it.
    """

    format: str = FORMAT
    name: str
    version: str
    input_type: str
    verdict_type: str
    reasoning: bool
    program: dict[str, JsonValue]
    training: Training | None = None
    dependencies: dict[str, str]


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
        self._reasoning = reasoning
        self._program: dspy.Module = (
            dspy.ChainOfThought(signature) if reasoning else dspy.Predict(signature)
        )
        self._name = name or f"{score_type_name(verdict_type)}-judge"
        self._lm = lm
        self._formatter = formatter or InputFormatter()
        self._tracer = get_tracer(tracer_provider)
        self._version = program_version(self._program, inputs, verdict_type)
        self._training: Training | None = None

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
    def training(self) -> Training | None:
        """How the judge was trained, if it was: the optimizer, the data and the scores."""
        return self._training

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

    def training_example(self, example: Example[InputT, VerdictT]) -> dspy.Example:
        """An example as DSPy trains on it: the input's fields, and people's verdict as labels.

        Raises:
            ValueError: The example has no verdict.
        """
        if example.verdict is None:
            raise ValueError(f"{example.id} has no verdict to train on")
        labels = example.verdict.model_dump(mode="json")
        return dspy.Example(**self.inputs(example.input), **labels).with_inputs(
            *self._input_type.model_fields
        )

    def snapshot(self) -> SavedJudge:
        """The judge as JSON, for ``save`` or any other store (ADR-0007)."""
        return SavedJudge(
            name=self._name,
            version=self._version,
            input_type=self._input_type.__qualname__,
            verdict_type=self._verdict_type.__qualname__,
            reasoning=self._reasoning,
            program=_without_lm(self._program.dump_state()),
            training=self._training,
            dependencies={"dspy": dspy.__version__, "evalr": _distribution_version("evalr")},
        )

    def save(self, path: str | os.PathLike[str]) -> None:
        """Write the judge to a JSON file."""
        Path(path).write_text(self.snapshot().model_dump_json(indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def restore[I: BaseModel, V: BaseModel](
        saved: SavedJudge,
        verdict_type: type[V],
        *,
        inputs: type[I],
        name: str | None = None,
        lm: dspy.BaseLM | None = None,
        formatter: InputFormatter | None = None,
        tracer_provider: trace.TracerProvider | None = None,
    ) -> "DspyJudge[I, V]":
        """Rebuild a saved judge for its types.

        The signature is derived from the types given, the program's state is loaded into it
        (never a language model: the judge uses ``lm``, or DSPy's), and the version is checked.

        Args:
            saved: The saved judge.
            verdict_type: The verdict type it was trained for.
            inputs: The input type it was trained for.
            name: A new name; the saved one by default.
            lm: The language model; DSPy's configured one by default.
            formatter: Renders the input; ``InputFormatter()`` by default.
            tracer_provider: Where evaluation spans go; the global provider by default.

        Raises:
            JudgeMismatch: It is not a saved judge, or the types have changed since it was
                saved, so its program would not match them.
        """
        if saved.format != FORMAT:
            raise JudgeMismatch(f"not a saved evalr judge: format {saved.format!r}")
        judge = DspyJudge(
            verdict_type,
            inputs=inputs,
            name=name or saved.name,
            reasoning=saved.reasoning,
            lm=lm,
            formatter=formatter,
            tracer_provider=tracer_provider,
        )
        judge._program.load_state(_without_lm(saved.program))
        judge._version = program_version(judge._program, inputs, verdict_type)
        if judge._version != saved.version:
            raise JudgeMismatch(
                f"{saved.name} was saved for {saved.input_type} and {saved.verdict_type} as they "
                f"were then (version {saved.version}); as {inputs.__qualname__} and "
                f"{verdict_type.__qualname__} are now it would be {judge._version}. "
                "Retrain it for the types as they are."
            )
        judge._training = saved.training
        return judge

    @staticmethod
    def load[I: BaseModel, V: BaseModel](
        path: str | os.PathLike[str],
        verdict_type: type[V],
        *,
        inputs: type[I],
        name: str | None = None,
        lm: dspy.BaseLM | None = None,
        formatter: InputFormatter | None = None,
        tracer_provider: trace.TracerProvider | None = None,
    ) -> "DspyJudge[I, V]":
        """Read a judge from a JSON file written by ``save``; see ``restore``.

        Raises:
            JudgeMismatch: It is not a saved judge, or the types have changed.
            pydantic.ValidationError: The file is not valid JSON of a saved judge.
        """
        saved = SavedJudge.model_validate_json(Path(path).read_text(encoding="utf-8"))
        return DspyJudge.restore(
            saved,
            verdict_type,
            inputs=inputs,
            name=name,
            lm=lm,
            formatter=formatter,
            tracer_provider=tracer_provider,
        )

    def trained(self, program: dspy.Module, training: Training) -> Self:
        """A copy of the judge with a trained program, versioned by it.

        Args:
            program: The trained program, of the same signature.
            training: How it was trained.
        """
        judge = copy.copy(self)
        judge._program = program
        judge._version = program_version(program, self._input_type, self._verdict_type)
        judge._training = training
        return judge

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
    canonical = json.dumps(
        {
            "program": program.dump_state(),
            "inputs": list(input_type.model_fields),
            "verdict": canonical_fields(verdict_type),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _without_lm(state: Mapping[str, object]) -> dict[str, Any]:
    """A program's state with every language-model configuration dropped."""
    result: dict[str, Any] = {}
    for key, value in state.items():
        if key == "lm":
            result[key] = None
        elif isinstance(value, dict):
            result[key] = _without_lm(cast(dict[str, object], value))
        else:
            result[key] = value
    return result
