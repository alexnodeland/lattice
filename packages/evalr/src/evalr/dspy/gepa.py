"""GEPA: fitting a DSPy judge to people's verdicts, and learning from their reasons.

GEPA (DSPy's reflective optimizer) runs the judge on training examples, shows a reflection model
where it disagreed with people and why, and rewrites the judge's instructions; a rewrite is kept
only if it agrees better with people on the validation examples. evalr's metric is per-field
agreement (``agreement_score``), and its feedback names each field the judge got wrong and
quotes people's own reasons: the verdict's text fields.
"""

import asyncio
from collections.abc import Callable
from typing import Literal

import dspy
from pydantic import BaseModel, JsonValue, ValidationError

from evalr.core import (
    Dataset,
    DatasetRef,
    FieldKind,
    Training,
    field_agreement,
    verdict_fields,
)
from evalr.dspy.judges import DspyJudge

__all__ = ["FeedbackMetric", "Gepa", "feedback_metric"]

type Budget = Literal["light", "medium", "heavy"]

type FeedbackMetric = Callable[
    [dspy.Example, dspy.Prediction, object, str | None, object], dspy.Prediction
]
"""GEPA's metric: gold example, prediction, trace, predictor name and its trace, to a score
with feedback."""


class Gepa:
    """GEPA as an ``Optimizer`` of DSPy judges.

    DSPy runs single-threaded here (``num_threads=1``): evaluation spans then keep their trace
    context, and the run is reproducible for a seed. The compile runs in a worker thread, so the
    event loop is not blocked.

    Example:
        ```python
        trained = await optimize(
            judge,
            train=train,
            validate=validate,
            optimizer=Gepa(reflection_lm=dspy.LM("openai/gpt-5"), auto="light"),
        )
        ```
    """

    def __init__(
        self,
        *,
        reflection_lm: dspy.BaseLM,
        auto: Budget | None = None,
        max_metric_calls: int | None = None,
        max_full_evals: int | None = None,
        reflection_minibatch_size: int = 3,
        use_merge: bool = True,
        seed: int = 0,
    ) -> None:
        """Configure GEPA. Give at most one budget; ``auto="light"`` by default.

        Args:
            reflection_lm: The model that reads the judge's mistakes and rewrites its
                instructions; usually stronger than the judge's.
            auto: A preset budget.
            max_metric_calls: A budget in metric calls.
            max_full_evals: A budget in full passes over the training and validation sets.
            reflection_minibatch_size: Training examples reflected on at a time.
            use_merge: Also merge successful candidates.
            seed: Makes the run reproducible.

        Raises:
            ValueError: More than one budget is given.
        """
        budgets = [b for b in (auto, max_metric_calls, max_full_evals) if b is not None]
        if len(budgets) > 1:
            raise ValueError("give one of auto, max_metric_calls and max_full_evals")
        self.reflection_lm = reflection_lm
        self.auto: Budget | None = auto if budgets else "light"
        self.max_metric_calls = max_metric_calls
        self.max_full_evals = max_full_evals
        self.reflection_minibatch_size = reflection_minibatch_size
        self.use_merge = use_merge
        self.seed = seed

    @property
    def settings(self) -> dict[str, JsonValue]:
        """The settings, as recorded on a trained judge."""
        return {
            "auto": self.auto,
            "max_metric_calls": self.max_metric_calls,
            "max_full_evals": self.max_full_evals,
            "reflection_minibatch_size": self.reflection_minibatch_size,
            "use_merge": self.use_merge,
            "seed": self.seed,
            "reflection_lm": self.reflection_lm.model,
        }

    async def optimize[InputT: BaseModel, VerdictT: BaseModel](
        self,
        judge: DspyJudge[InputT, VerdictT],
        /,
        *,
        train: Dataset[InputT, VerdictT],
        validate: Dataset[InputT, VerdictT],
    ) -> DspyJudge[InputT, VerdictT]:
        """Train the judge's instructions on ``train``, keeping what does best on ``validate``.

        Returns:
            A new judge with the trained program, its own version, and a ``Training`` record
            with the validation agreement before and after.
        """
        optimizer = dspy.GEPA(
            feedback_metric(judge),
            auto=self.auto,
            max_metric_calls=self.max_metric_calls,
            max_full_evals=self.max_full_evals,
            reflection_minibatch_size=self.reflection_minibatch_size,
            reflection_lm=self.reflection_lm,
            use_merge=self.use_merge,
            num_threads=1,
            track_stats=True,
            seed=self.seed,
        )
        trainset = [judge.training_example(e) for e in train]
        valset = [judge.training_example(e) for e in validate]

        def compile() -> dspy.Module:
            with judge.lm_context():
                return optimizer.compile(judge.program, trainset=trainset, valset=valset)

        program = await asyncio.to_thread(compile)
        results = program.detailed_results
        return judge.trained(
            program,
            Training(
                optimizer="gepa",
                settings=self.settings,
                base_version=judge.version,
                train=DatasetRef.of(train),
                validation=DatasetRef.of(validate),
                score_before=results.val_aggregate_scores[0],
                score_after=results.val_aggregate_scores[results.best_idx],
            ),
        )


def feedback_metric[InputT: BaseModel, VerdictT: BaseModel](
    judge: DspyJudge[InputT, VerdictT],
) -> FeedbackMetric:
    """GEPA's metric for a judge: per-field agreement with people, with textual feedback.

    The score is the mean of ``field_agreement`` (1 when people gave no scored field). The
    feedback names each field the judge got wrong, with both answers, and quotes people's text
    fields (their reasons), so the reflection model learns why people judged as they did. An
    answer that is not a valid verdict scores 0, and the feedback says why.
    """
    verdict_type = judge.verdict_type
    texts = [f.name for f in verdict_fields(verdict_type) if f.kind is FieldKind.TEXT]

    def metric(
        gold: dspy.Example,
        pred: dspy.Prediction,
        _trace: object = None,
        _pred_name: str | None = None,
        _pred_trace: object = None,
    ) -> dspy.Prediction:
        expected = verdict_type.model_validate(gold.labels().toDict())
        reasons = [
            f"People's {name}: {value}"
            for name in texts
            if (value := getattr(expected, name)) is not None
        ]
        try:
            predicted = judge.parse(pred)
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
            )
            lines = [f"The answer was not a valid {verdict_type.__name__}: {problems}.", *reasons]
            return dspy.Prediction(score=0.0, feedback="\n".join(lines))
        agreements = field_agreement(expected, predicted)
        wrong = [
            f"{name}: you said {getattr(predicted, name)!r}, "
            f"people said {getattr(expected, name)!r}."
            for name, agreement in agreements.items()
            if agreement < 1.0
        ]
        score = sum(agreements.values()) / len(agreements) if agreements else 1.0
        lines = wrong or ["You agreed with people on every field."]
        return dspy.Prediction(score=score, feedback="\n".join([*lines, *reasons]))

    return metric
