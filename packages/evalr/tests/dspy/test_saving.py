import json
from pathlib import Path
from typing import Annotated

import dspy
import pytest
from pydantic import BaseModel, Field

from evalr.core import optimize
from evalr.dspy import FORMAT, DspyJudge, Gepa, JudgeMismatch, SavedJudge

from .scripted import MARKER, InstructionAware, Reply, Score, pluses, reflection_lm


async def trained_judge() -> DspyJudge[Reply, Score]:
    judge = DspyJudge(Score, inputs=Reply, lm=InstructionAware())
    return await optimize(
        judge,
        train=pluses("train", [2, 3, 4, 5]),
        validate=pluses("validate", [1, 2, 3, 5]),
        optimizer=Gepa(
            reflection_lm=reflection_lm(),
            max_metric_calls=12,
            reflection_minibatch_size=2,
            use_merge=False,
        ),
    )


async def test_a_trained_judge_round_trips_through_a_file(tmp_path: Path) -> None:
    trained = await trained_judge()
    path = tmp_path / "score-judge.json"
    trained.save(path)

    saved = json.loads(path.read_text())
    assert saved["format"] == FORMAT
    assert (saved["name"], saved["version"]) == ("score-judge", trained.version)
    assert (saved["input_type"], saved["verdict_type"], saved["reasoning"]) == (
        "Reply",
        "Score",
        False,
    )
    assert set(saved["dependencies"]) == {"dspy", "evalr"}
    assert saved["training"]["optimizer"] == "gepa"

    loaded = DspyJudge.load(path, Score, inputs=Reply, lm=InstructionAware())
    assert (loaded.name, loaded.version, loaded.instructions) == (
        "score-judge",
        trained.version,
        MARKER,
    )
    assert loaded.training == trained.training
    verdict = await loaded.evaluate(Reply(request="r", reply="++++"))
    assert (verdict.value.rating, verdict.version) == (4, trained.version)


async def test_a_reasoning_judge_round_trips_and_can_be_renamed() -> None:
    judge = DspyJudge(Score, inputs=Reply, reasoning=True, instructions="Be fair.")
    loaded = DspyJudge.restore(judge.snapshot(), Score, inputs=Reply, name="fair")
    assert isinstance(loaded.program, dspy.ChainOfThought)
    assert (loaded.name, loaded.version, loaded.instructions) == ("fair", judge.version, "Be fair.")
    assert loaded.training is None


async def test_changed_types_are_refused() -> None:
    class Stricter(BaseModel):
        rating: Annotated[int, Field(ge=1, le=10, description="How good the reply is")]
        resolved: bool
        reason: str | None = None

    snapshot = DspyJudge(Score, inputs=Reply).snapshot()
    with pytest.raises(JudgeMismatch, match="Retrain it for the types as they are"):
        DspyJudge.restore(snapshot, Stricter, inputs=Reply)


def test_other_formats_are_refused() -> None:
    snapshot = DspyJudge(Score, inputs=Reply).snapshot().model_copy(update={"format": "x/1"})
    with pytest.raises(JudgeMismatch, match="not a saved evalr judge"):
        DspyJudge.restore(snapshot, Score, inputs=Reply)


def test_a_saved_language_model_is_never_loaded() -> None:
    judge = DspyJudge(Score, inputs=Reply, reasoning=True)
    state = judge.snapshot().model_dump(mode="json")
    state["program"]["predict"]["lm"] = {"model": "somewhere/else"}
    loaded = DspyJudge.restore(SavedJudge.model_validate(state), Score, inputs=Reply)
    assert loaded.program.dump_state()["predict"]["lm"] is None
