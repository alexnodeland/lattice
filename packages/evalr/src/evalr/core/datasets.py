"""Examples and datasets: inputs with what people, or a reference, say about them."""

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from functools import cached_property
from typing import Annotated, Self

from pydantic import BaseModel, Field, JsonValue

from evalr.core.fields import verdict_fields

__all__ = ["Dataset", "DatasetNotFound", "DuplicateExample", "Example", "split_bucket"]


class Example[InputT: BaseModel, VerdictT: BaseModel](BaseModel, frozen=True):
    """One input, with the verdict people gave it, a reference output, or both.

    Attributes:
        id: A stable identifier. Splits are hashed from it, and syncing uses it, so an example
            keeps its id for life: derive it from the feedback or item it came from.
        input: What an evaluator judges: a thread, a run, an artifact version.
        verdict: The verdict people gave the input, when there is one. Judges are trained and
            measured against it.
        reference: A reference output for the system being evaluated, such as the answer it
            should give, for evaluators that compare against one.
        trace_id: The OpenTelemetry trace the input came from, as 32 hex digits, so datasets
            and experiments link back to it.
        metadata: Anything else worth keeping with the example, as JSON.
    """

    id: Annotated[str, Field(min_length=1)]
    input: InputT
    verdict: VerdictT | None = None
    reference: JsonValue = None
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])


class DuplicateExample(ValueError):
    """Two examples in one dataset share an id."""


class DatasetNotFound(LookupError):
    """A store has no dataset of that name, or no such revision of it."""


def split_bucket(example_id: str, salt: str = "") -> float:
    """Place an example in ``[0, 1)`` by a hash of its id.

    The position depends on nothing but the id and the salt, so it is the same in every process
    and every run, and adding or removing other examples never moves it.

    Args:
        example_id: The example's id.
        salt: Changes every position at once, for an independent split of the same examples.
    """
    digest = hashlib.sha256(f"{salt}\x00{example_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class Dataset[InputT: BaseModel, VerdictT: BaseModel]:
    """An immutable, named collection of examples of one input type and one verdict type.

    Example:
        ```python
        dataset = Dataset(
            "helpfulness",
            examples,
            input_type=Thread,
            verdict_type=Helpfulness,
        )
        train, validate = dataset.labelled().split(0.2)
        ```
    """

    def __init__(
        self,
        name: str,
        examples: Iterable[Example[InputT, VerdictT]],
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
        description: str = "",
    ) -> None:
        """Collect examples into a dataset.

        Args:
            name: The dataset's name, used when it is synced to Langfuse or Hugging Face.
            examples: The examples, in any order. Their ids must be unique.
            input_type: The Pydantic model of every example's input.
            verdict_type: The Pydantic model of every example's verdict.
            description: What the dataset holds, for people browsing it.

        Raises:
            DuplicateExample: Two examples share an id.
            UnsupportedField: The verdict type has a field evaluators cannot judge.
        """
        verdict_fields(verdict_type)
        self.name = name
        self.description = description
        self.input_type = input_type
        self.verdict_type = verdict_type
        self.examples: tuple[Example[InputT, VerdictT], ...] = tuple(examples)
        self._by_id = {e.id: e for e in self.examples}
        if len(self._by_id) != len(self.examples):
            counts = Counter(e.id for e in self.examples)
            duplicates = sorted(i for i, n in counts.items() if n > 1)
            raise DuplicateExample(f"{name}: duplicate example ids {duplicates}")

    @staticmethod
    def from_records[I: BaseModel, V: BaseModel](
        name: str,
        records: Iterable[Mapping[str, JsonValue]],
        *,
        input_type: type[I],
        verdict_type: type[V],
        description: str = "",
    ) -> "Dataset[I, V]":
        """Load a dataset from JSON records, as written by ``records``.

        Raises:
            pydantic.ValidationError: A record is not a valid example of these types.
        """
        example_type = Example[input_type, verdict_type]
        return Dataset(
            name,
            (example_type.model_validate(r) for r in records),
            input_type=input_type,
            verdict_type=verdict_type,
            description=description,
        )

    def records(self) -> list[dict[str, JsonValue]]:
        """The examples as JSON records, in order: one object per example."""
        return [e.model_dump(mode="json") for e in self.examples]

    @cached_property
    def version(self) -> str:
        """A hash of the examples' content, independent of their order: 16 hex digits.

        Any change to any example changes it, so a trained judge records the exact data it
        was trained on. Numbers are hashed by value, as JSON reads them (``1.0`` and ``1`` are
        one number), so a dataset keeps its version through stores that write whole numbers
        without a decimal point, as Langfuse does.
        """
        records = [_whole(r) for r in sorted(self.records(), key=lambda r: str(r["id"]))]
        canonical = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def __len__(self) -> int:
        return len(self.examples)

    def __iter__(self) -> Iterator[Example[InputT, VerdictT]]:
        return iter(self.examples)

    def __contains__(self, example_id: object) -> bool:
        return example_id in self._by_id

    def __getitem__(self, example_id: str) -> Example[InputT, VerdictT]:
        return self._by_id[example_id]

    def __repr__(self) -> str:
        return (
            f"Dataset({self.name!r}, {len(self)} examples, "
            f"{self.input_type.__name__} -> {self.verdict_type.__name__})"
        )

    def _with(self, examples: Iterable[Example[InputT, VerdictT]]) -> Self:
        return type(self)(
            self.name,
            examples,
            input_type=self.input_type,
            verdict_type=self.verdict_type,
            description=self.description,
        )

    def filter(self, predicate: Callable[[Example[InputT, VerdictT]], bool]) -> Self:
        """The examples for which the predicate holds, as a dataset of the same name."""
        return self._with(e for e in self.examples if predicate(e))

    def labelled(self) -> Self:
        """The examples that have a verdict from people."""
        return self.filter(lambda e: e.verdict is not None)

    def split(self, validate: float = 0.2, *, salt: str = "") -> tuple[Self, Self]:
        """Split into training and validation examples, deterministically by id.

        An example goes to validation when ``split_bucket(id, salt) < validate``. So an example
        never moves between the two as examples are added or removed, and raising the fraction
        only moves examples from training to validation.

        Args:
            validate: The expected share of examples in validation, from 0 to 1.
            salt: Gives an independent split of the same examples.

        Returns:
            The training and validation datasets, each keeping this dataset's order.

        Raises:
            ValueError: The fraction is outside ``[0, 1]``.
        """
        if not 0.0 <= validate <= 1.0:
            raise ValueError(f"validate must be between 0 and 1; got {validate}")
        held_out = {e.id for e in self.examples if split_bucket(e.id, salt) < validate}
        return (
            self.filter(lambda e: e.id not in held_out),
            self.filter(lambda e: e.id in held_out),
        )


def _whole(value: JsonValue) -> JsonValue:
    """JSON with every whole-number float as the integer it equals."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_whole(item) for item in value]
    if isinstance(value, dict):
        return {key: _whole(item) for key, item in value.items()}
    return value
