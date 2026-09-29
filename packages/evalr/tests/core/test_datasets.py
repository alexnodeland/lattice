import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, JsonValue, ValidationError

from evalr import Dataset, Example, UnsupportedField
from evalr.core import DuplicateExample, split_bucket

from .models import Helpfulness, Thread

Ex = Example[Thread, Helpfulness]


def example(i: int, *, labelled: bool = True) -> Example[Thread, Helpfulness]:
    verdict = Helpfulness(rating=1 + i % 5, resolved=i % 2 == 0) if labelled else None
    return Ex(id=f"ex-{i}", input=Thread(messages=[f"message {i}"]), verdict=verdict)


def dataset(n: int = 10) -> Dataset[Thread, Helpfulness]:
    return Dataset(
        "helpfulness",
        (example(i, labelled=i % 3 != 0) for i in range(n)),
        input_type=Thread,
        verdict_type=Helpfulness,
        description="Replies people rated",
    )


def test_a_dataset_holds_its_examples_in_order() -> None:
    data = dataset()
    assert len(data) == 10
    assert [e.id for e in data] == [f"ex-{i}" for i in range(10)]
    assert "ex-3" in data
    assert "nope" not in data
    assert data["ex-4"].input.messages == ["message 4"]
    assert repr(data) == "Dataset('helpfulness', 10 examples, Thread -> Helpfulness)"


def test_ids_are_unique() -> None:
    with pytest.raises(DuplicateExample, match=r"\['ex-1'\]"):
        Dataset(
            "d",
            [example(1), example(2), example(1)],
            input_type=Thread,
            verdict_type=Helpfulness,
        )


def test_example_ids_are_not_empty() -> None:
    with pytest.raises(ValidationError):
        Ex(id="", input=Thread(messages=[]))


def test_the_verdict_type_must_be_judgeable() -> None:
    class Listy(BaseModel):
        tags: list[str]

    with pytest.raises(UnsupportedField):
        Dataset("d", [], input_type=Thread, verdict_type=Listy)


def test_records_round_trip() -> None:
    data = dataset()
    rich = Ex(
        id="rich",
        input=Thread(messages=["a"]),
        verdict=Helpfulness(rating=5, resolved=True, reason="great"),
        reference={"answer": "a refund"},
        trace_id="0af7651916cd43dd8448eb211c80319c",
        metadata={"source": "feedback", "tags": ["x"]},
    )
    data = Dataset(data.name, [*data, rich], input_type=Thread, verdict_type=Helpfulness)
    loaded = Dataset.from_records(
        "copy", data.records(), input_type=Thread, verdict_type=Helpfulness, description="c"
    )
    assert list(loaded) == list(data)
    assert (loaded.name, loaded.description) == ("copy", "c")
    assert loaded.version == data.version


def test_invalid_records_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Dataset.from_records(
            "d",
            [{"id": "x", "input": {"messages": 3}}],
            input_type=Thread,
            verdict_type=Helpfulness,
        )


def test_the_version_is_a_hash_of_the_content_not_the_order() -> None:
    data = dataset()
    shuffled = Dataset(
        "other name", reversed(data.examples), input_type=Thread, verdict_type=Helpfulness
    )
    assert shuffled.version == data.version
    assert len(data.version) == 16
    changed = Dataset(
        "helpfulness",
        [*data.examples[:-1], example(9, labelled=not data.examples[-1].verdict)],
        input_type=Thread,
        verdict_type=Helpfulness,
    )
    assert changed.version != data.version


def test_the_version_takes_whole_floats_for_the_integers_they_equal() -> None:
    def with_numbers(reference: JsonValue, weight: float) -> Dataset[Thread, Helpfulness]:
        rich = Ex(
            id="rich",
            input=Thread(messages=["a"]),
            reference=reference,
            metadata={"weight": weight, "nested": {"scores": [weight, 0.5]}},
        )
        return Dataset("d", [rich], input_type=Thread, verdict_type=Helpfulness)

    as_floats = with_numbers({"score": 1.0, "steps": [2.0, 3.0]}, 2.0)
    as_integers = with_numbers({"score": 1, "steps": [2, 3]}, 2)
    assert as_floats.version == as_integers.version
    assert with_numbers({"score": 1.5, "steps": [2, 3]}, 2).version != as_integers.version


def test_labelled_keeps_the_examples_with_a_verdict() -> None:
    labelled = dataset().labelled()
    assert [e.id for e in labelled] == [f"ex-{i}" for i in range(10) if i % 3 != 0]
    assert labelled.name == "helpfulness"
    assert labelled.description == "Replies people rated"


def test_filter_keeps_the_types() -> None:
    kept = dataset().filter(lambda e: e.id.endswith("1"))
    assert [e.id for e in kept] == ["ex-1"]
    assert (kept.input_type, kept.verdict_type) == (Thread, Helpfulness)


def test_a_split_partitions_the_examples() -> None:
    data = dataset(200)
    train, validate = data.split(0.25)
    assert {e.id for e in train} | {e.id for e in validate} == {e.id for e in data}
    assert not {e.id for e in train} & {e.id for e in validate}
    assert 20 < len(validate) < 80
    assert [e.id for e in validate] == [e.id for e in data if e.id in validate]


def test_the_salt_gives_an_independent_split() -> None:
    data = dataset(200)
    _, one = data.split(0.5)
    _, other = data.split(0.5, salt="fold-2")
    assert {e.id for e in one} != {e.id for e in other}


@pytest.mark.parametrize("fraction", [-0.1, 1.5])
def test_the_fraction_is_a_share(fraction: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        dataset().split(fraction)


def test_edge_fractions() -> None:
    data = dataset()
    assert len(data.split(0.0)[1]) == 0
    assert len(data.split(1.0)[0]) == 0


ids = st.lists(st.text(min_size=1, max_size=12), unique=True, max_size=40)


@given(ids, ids, st.floats(0.0, 1.0))
def test_adding_examples_never_moves_existing_ones(
    first: list[str], more: list[str], fraction: float
) -> None:
    def build(names: list[str]) -> Dataset[Thread, Helpfulness]:
        return Dataset(
            "d",
            (Ex(id=n, input=Thread(messages=[])) for n in names),
            input_type=Thread,
            verdict_type=Helpfulness,
        )

    before = build(first)
    after = build(first + [m for m in more if m not in first])
    _, held_before = before.split(fraction)
    _, held_after = after.split(fraction)
    assert {e.id for e in held_before} == {e.id for e in held_after if e.id in before}


@given(st.text(min_size=1), st.floats(0.0, 1.0), st.floats(0.0, 1.0))
def test_raising_the_fraction_only_moves_examples_into_validation(
    example_id: str, low: float, high: float
) -> None:
    low, high = sorted((low, high))
    position = split_bucket(example_id)
    assert 0.0 <= position < 1.0
    assert (position < low) <= (position < high)


def test_buckets_are_pinned_by_the_hash_of_the_id() -> None:
    # sha256 of "\x00ex-1", first 8 bytes over 2**64: the same in every process and release.
    assert split_bucket("ex-1") == 0.16347085753066165
    assert split_bucket("ex-1", salt="s") == 0.17876188184984315
