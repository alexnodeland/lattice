import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from evalr.core import Example
from evalr.hf import import_dataset

COMMIT = "0123456789abcdef0123456789abcdef01234567"


class Question(BaseModel):
    text: str


class Label(BaseModel):
    correct: bool


def write(directory: Path, rows: list[dict[str, Any]]) -> Path:
    directory.mkdir(parents=True)
    (directory / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return directory


async def test_evalr_records_import_as_they_are(tmp_path: Path) -> None:
    rows = [
        {"id": f"q{i}", "input": {"text": f"question {i}"}, "verdict": {"correct": i % 2 == 0}}
        for i in range(3)
    ]
    path = write(tmp_path / "records", rows)
    dataset = await import_dataset(
        str(path),
        revision=COMMIT,
        input_type=Question,
        verdict_type=Label,
        name="questions",
        description="Imported",
        cache_dir=str(tmp_path / "cache"),
    )
    assert (dataset.name, dataset.description, len(dataset)) == ("questions", "Imported", 3)
    assert dataset["q1"].verdict == Label(correct=False)


async def test_other_rows_are_converted(tmp_path: Path) -> None:
    rows = [
        {"question": "2 + 2?", "answer": "4", "label": 1},
        {"question": "1 + 1?", "answer": "3", "label": 0},
    ]
    path = write(tmp_path / "other", rows)

    def to_example(row: dict[str, Any]) -> Example[Question, Label]:
        return Example[Question, Label](
            id=row["question"],
            input=Question(text=f"{row['question']} {row['answer']}"),
            verdict=Label(correct=row["label"] == 1),
        )

    dataset = await import_dataset(
        str(path),
        revision=COMMIT,
        input_type=Question,
        verdict_type=Label,
        to_example=to_example,
        cache_dir=str(tmp_path / "cache"),
    )
    assert dataset.name == str(path)
    assert [e.verdict for e in dataset] == [Label(correct=True), Label(correct=False)]


@pytest.mark.parametrize("revision", ["main", "v1", "0123456"])
async def test_only_a_commit_can_be_imported(revision: str) -> None:
    with pytest.raises(ValueError, match="full commit hash"):
        await import_dataset("org/d", revision=revision, input_type=Question, verdict_type=Label)
