"""Decision evaluators: a pydantic-ai agent on a decision model, with the verdict as its output."""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Self

from opentelemetry import trace
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.decision import DecisionHandOff, DecisionModelSettings

from evalr.core import (
    Formatter,
    HandOff,
    InputFormatter,
    Training,
    Verdict,
    canonical_fields,
    get_tracer,
    judging,
    score_type_name,
)
from evalr.decision.views import DecisionView, decision_view

__all__ = ["DEFAULT_BOOLEAN_THRESHOLD", "DEFAULT_MODEL", "Decision", "DecisionEvaluator"]

DEFAULT_MODEL = "typesafe:jev-latest"
"""TypeSafe's Jev, the latest version. Pin a version (``typesafe:jev-1.13.0``) once calibrated."""

DEFAULT_BOOLEAN_THRESHOLD = 0.5
"""pydantic-ai's threshold for a yes, when none is set."""


@dataclass(frozen=True, slots=True)
class Decision[VerdictT: BaseModel]:
    """What a decision model answered for one input, before any hand-off.

    Attributes:
        value: The verdict, with the fields the model cannot fill at their defaults.
        confidence: The probability that each field's value is right, where the model gives
            one: a choice's probability, and a yes-or-no answer's probability of the answer
            given.
        probabilities: For each yes-or-no field, the model's probability of yes, from which
            the answer follows by the boolean threshold.
        model: The model that answered, as it named itself (``jev-1.13.0``).
        cost: US dollars, when known.
    """

    value: VerdictT
    confidence: dict[str, float]
    probabilities: dict[str, float]
    model: str | None
    cost: float | None


class DecisionEvaluator[InputT: BaseModel, VerdictT: BaseModel]:
    """A decision model as an evaluator: fast, cheap typed answers with calibrated confidence.

    It is a pydantic-ai ``Agent`` on a decision model (TypeSafe's Jev by default) whose output
    type is the verdict type's decision-only view (``decision_view``): each field becomes a typed
    question, and the answers carry probabilities. Fields the model cannot fill, such as free
    text, keep their defaults; ``Fallback`` hands inputs to a language-model judge that fills
    them.

    It hands off (raises ``HandOff``) when pydantic-ai does (``DecisionHandOff``), and when any
    field's confidence is below ``min_confidence``. Both thresholds, and pydantic-ai's
    ``decision_boolean_threshold``, are what ``ThresholdCalibration`` tunes.

    Example:
        ```python
        decider = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)
        evaluator = Fallback(decider, DspyJudge(Helpfulness, inputs=Thread))
        ```
    """

    def __init__(
        self,
        verdict_type: type[VerdictT],
        *,
        inputs: type[InputT],
        model: Model | str = DEFAULT_MODEL,
        boolean_threshold: float | None = None,
        min_confidence: float | None = None,
        instructions: str | None = None,
        name: str | None = None,
        formatter: Formatter[InputT] | None = None,
        tracer_provider: trace.TracerProvider | None = None,
    ) -> None:
        """Build a decision evaluator.

        Args:
            verdict_type: The verdict it gives.
            inputs: The input it reads, rendered as the model's state by the formatter.
            model: A pydantic-ai decision model, or its name. Credentials are needed only
                when it first runs (``TYPESAFE_API_KEY`` for Jev).
            boolean_threshold: The probability of yes at which a yes-or-no field is yes:
                pydantic-ai's ``decision_boolean_threshold``, 0.5 by default.
            min_confidence: Hand off when any field's confidence is below this.
            instructions: Background the model reads with every question.
            name: The evaluator's name; ``{verdict type}-decision`` by default.
            formatter: Renders the input as the model's state; within 30,000 estimated tokens
                by default, under Jev's 32K limit.
            tracer_provider: Where evaluation spans go; the global provider by default.

        Raises:
            UnsupportedField: A field the model cannot fill has no default.
            ValueError: A threshold is out of range.
        """
        if boolean_threshold is not None and not 0.0 < boolean_threshold < 1.0:
            raise ValueError(f"boolean_threshold must be between 0 and 1; got {boolean_threshold}")
        if min_confidence is not None and not 0.0 <= min_confidence <= 1.0:
            raise ValueError(f"min_confidence must be between 0 and 1; got {min_confidence}")
        self._verdict_type = verdict_type
        self._input_type = inputs
        self._view = decision_view(verdict_type)
        self._model_name = model if isinstance(model, str) else f"{model.system}:{model.model_name}"
        self._boolean_threshold = boolean_threshold
        self._min_confidence = min_confidence
        self._instructions = instructions
        self._name = name or f"{score_type_name(verdict_type)}-decision"
        self._agent = Agent(
            model,
            output_type=self._view.model,
            instructions=instructions,
            name=self._name,
            defer_model_check=True,
        )
        self._formatter: Formatter[InputT] = formatter or InputFormatter(max_tokens=30_000)
        self._tracer = get_tracer(tracer_provider)
        self._training: Training | None = None
        self._version = self._hash()

    @property
    def name(self) -> str:
        """The evaluator's name."""
        return self._name

    @property
    def version(self) -> str:
        """A hash of the model's name, the types, the instructions and the thresholds."""
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
    def view(self) -> DecisionView:
        """The decision-only view of the verdict type."""
        return self._view

    @property
    def model_name(self) -> str:
        """The decision model's name, as given or as ``{system}:{model}``."""
        return self._model_name

    @property
    def boolean_threshold(self) -> float:
        """The probability of yes at which a yes-or-no field is yes."""
        return self._boolean_threshold or DEFAULT_BOOLEAN_THRESHOLD

    @property
    def min_confidence(self) -> float | None:
        """The confidence below which it hands off, if any."""
        return self._min_confidence

    @property
    def training(self) -> Training | None:
        """How its thresholds were calibrated, if they were."""
        return self._training

    async def decide(self, input: InputT) -> Decision[VerdictT]:
        """Ask the decision model, without handing off.

        Raises:
            pydantic_ai.models.decision.DecisionHandOff: pydantic-ai handed the step off.
        """
        settings = DecisionModelSettings(decision_boolean_threshold=self.boolean_threshold)
        result = await self._agent.run(self._formatter(input), model_settings=settings)
        output = result.output
        details: dict[str, Any] = result.response.provider_details or {}
        reported: dict[str, Any] = details.get("confidence", {})
        confidence: dict[str, float] = {}
        probabilities: dict[str, float] = {}
        for name in self._view.decided:
            if name not in reported:
                continue
            answer: object = getattr(output, name)
            given = float(reported[name])
            if isinstance(answer, bool):
                probabilities[name] = _probability_of_yes(answer, given, self.boolean_threshold)
                confidence[name] = probabilities[name] if answer else 1 - probabilities[name]
            else:
                confidence[name] = given
        cost = result.usage.cost
        return Decision(
            value=self._verdict_type.model_validate(output.model_dump()),
            confidence=confidence,
            probabilities=probabilities,
            model=result.response.model_name,
            cost=None if cost is None else float(cost),
        )

    async def evaluate(self, input: InputT, /) -> Verdict[VerdictT]:
        """Judge one input, or hand it off.

        Raises:
            HandOff: pydantic-ai handed the step off, or a field's confidence is below
                ``min_confidence``.
        """
        cause: DecisionHandOff | None = None
        with judging(
            self._tracer,
            evaluator=self._name,
            version=self._version,
            verdict_type=self._verdict_type,
        ) as run:
            try:
                decision = await self.decide(input)
            except DecisionHandOff as error:
                cause, reason = error, f"the decision model handed off: {error}"
            else:
                run.span.set_attribute("gen_ai.response.model", decision.model or "")
                reason = self._unsure(decision.confidence)
                if reason is None:
                    return run.verdict(
                        decision.value, confidence=decision.confidence, cost=decision.cost
                    )
            run.span.set_attributes({"evalr.handed_off": True, "evalr.hand_off.reason": reason})
        raise HandOff(reason) from cause

    def calibrated(
        self, *, boolean_threshold: float, min_confidence: float | None, training: Training
    ) -> Self:
        """A copy with calibrated thresholds, versioned by them.

        Raises:
            ValueError: A threshold is out of range.
        """
        if not 0.0 < boolean_threshold < 1.0:
            raise ValueError(f"boolean_threshold must be between 0 and 1; got {boolean_threshold}")
        evaluator = copy.copy(self)
        evaluator._boolean_threshold = boolean_threshold
        evaluator._min_confidence = min_confidence
        evaluator._training = training
        evaluator._version = evaluator._hash()
        return evaluator

    def _unsure(self, confidence: dict[str, float]) -> str | None:
        if self._min_confidence is None or not confidence:
            return None
        field, lowest = min(confidence.items(), key=lambda item: item[1])
        if lowest >= self._min_confidence:
            return None
        return f"confidence in {field} is {lowest:.2f}, below {self._min_confidence}"

    def _hash(self) -> str:
        canonical = json.dumps(
            {
                "model": self._model_name,
                "inputs": list(self._input_type.model_fields),
                "verdict": canonical_fields(self._verdict_type),
                "decided": list(self._view.decided),
                "instructions": self._instructions,
                "boolean_threshold": self.boolean_threshold,
                "min_confidence": self._min_confidence,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _probability_of_yes(answer: bool, confidence: float, threshold: float) -> float:
    """Undo pydantic-ai's yes-or-no confidence, which is the distance from the threshold.

    pydantic-ai reports ``(p - t) / (1 - t)`` for a yes and ``(t - p) / t`` for a no, where
    ``p`` is the model's probability of yes and ``t`` the threshold.
    """
    p = threshold + confidence * (1 - threshold) if answer else threshold - confidence * threshold
    return min(1.0, max(0.0, p))
