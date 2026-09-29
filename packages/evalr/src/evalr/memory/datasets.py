"""An in-memory dataset store."""

from dataclasses import dataclass, field

from pydantic import BaseModel, JsonValue

from evalr.core import Dataset, DatasetNotFound

__all__ = ["InMemoryDatasetStore"]


@dataclass
class _Stored:
    description: str
    latest: str
    revisions: dict[str, list[dict[str, JsonValue]]] = field(
        default_factory=dict[str, list[dict[str, JsonValue]]]
    )


class InMemoryDatasetStore:
    """Keeps datasets as JSON records in memory, one revision per distinct content.

    A revision is the dataset's content hash (``Dataset.version``), so saving the same examples
    again makes no new revision. Loading validates the records again, as a real store does.
    """

    def __init__(self) -> None:
        """Start empty."""
        self._datasets: dict[str, _Stored] = {}

    async def save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT], /
    ) -> str:
        """Store the dataset's records under its name, and return its content hash."""
        revision = dataset.version
        stored = self._datasets.setdefault(dataset.name, _Stored(dataset.description, revision))
        stored.revisions[revision] = dataset.records()
        stored.description = dataset.description
        stored.latest = revision
        return revision

    async def load[InputT: BaseModel, VerdictT: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
        revision: str | None = None,
    ) -> Dataset[InputT, VerdictT]:
        """Load the latest revision of a dataset, or the one given.

        Raises:
            DatasetNotFound: No dataset has the name, or it has no such revision.
        """
        stored = self._datasets.get(name)
        if stored is None:
            raise DatasetNotFound(f"no dataset named {name!r}")
        records = stored.revisions.get(revision or stored.latest)
        if records is None:
            raise DatasetNotFound(f"dataset {name!r} has no revision {revision!r}")
        return Dataset.from_records(
            name,
            records,
            input_type=input_type,
            verdict_type=verdict_type,
            description=stored.description,
        )
