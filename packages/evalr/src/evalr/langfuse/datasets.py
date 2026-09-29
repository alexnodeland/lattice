"""Langfuse datasets as a ``DatasetStore``.

A dataset is a Langfuse dataset of the same name, and each example an item. Item ids are derived
from the dataset's name and the example's id (UUID 5), so syncing again updates items rather
than adding more; Langfuse's item ids are unique across a project, hence the dataset's name.

| Item | Holds |
|---|---|
| ``input`` | The example's input, as JSON |
| ``expectedOutput`` | ``{"verdict": ..., "reference": ...}`` |
| ``metadata`` | The example's metadata, with its id under ``evalr`` |
| ``sourceTraceId`` | The trace the example came from |

Langfuse versions a dataset's items by time, so a revision is a time at which Langfuse held the
dataset as saved, and loading a revision reads the items as they were then. Saving the same
content again returns the same revision. Examples no longer in the dataset are archived, not
deleted. An item written without a source trace keeps the one it had, so when an example loses
its trace, its item is deleted and written anew; earlier revisions keep the trace.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, cast

from langfuse import Langfuse
from langfuse.api import DatasetItem, DatasetStatus, NotFoundError
from pydantic import BaseModel, JsonValue

from evalr.core import Dataset, DatasetNotFound, Example

__all__ = ["ITEM_NAMESPACE", "LangfuseDatasetStore", "item_id"]

ITEM_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/alexnodeland/evalr/items")
"""The namespace of dataset item ids."""

_EVALR = "evalr"


def item_id(dataset: str, example_id: str) -> str:
    """The Langfuse item id of an example: a UUID 5 of the dataset's name and the example's id."""
    return str(uuid.uuid5(ITEM_NAMESPACE, f"{dataset}/{example_id}"))


class LangfuseDatasetStore:
    """Saves datasets to Langfuse, and loads them from it, through a ``Langfuse`` client.

    The client is the application's, configured as it likes; the store makes no other
    connection. Its calls are synchronous, so they run in a worker thread.
    """

    def __init__(self, client: Langfuse) -> None:
        """Use a Langfuse client.

        Args:
            client: The application's client.
        """
        self.client = client

    async def save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT], /
    ) -> str:
        """Create or update the Langfuse dataset, item by item, and archive what was removed.

        Only items whose content changed are written.

        Returns:
            A time at which Langfuse held the dataset as saved, in ISO 8601, which ``load``
            accepts: the same time for the same content.
        """
        return await asyncio.to_thread(self._save, dataset)

    async def load[InputT: BaseModel, VerdictT: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
        revision: str | None = None,
    ) -> Dataset[InputT, VerdictT]:
        """Read the dataset's active items, as they are or as they were at ``revision``.

        Items not written by evalr are read as they are: the input as the input, and the
        expected output as the verdict.

        Raises:
            DatasetNotFound: Langfuse has no dataset of that name, or the revision is not a time.
            pydantic.ValidationError: The items are not examples of these types.
        """
        try:
            version = datetime.fromisoformat(revision) if revision is not None else None
        except ValueError:
            raise DatasetNotFound(f"dataset {name!r} has no revision {revision!r}") from None
        description, items = await asyncio.to_thread(self._items, name, version)
        active = sorted(
            (i for i in items if i.status == DatasetStatus.ACTIVE),
            key=lambda i: (i.created_at, i.id),
        )
        return Dataset.from_records(
            name,
            [_record(item) for item in active],
            input_type=input_type,
            verdict_type=verdict_type,
            description=description,
        )

    def _items(self, name: str, version: datetime | None) -> tuple[str, list[DatasetItem]]:
        try:
            found = self.client.get_dataset(name, version=version)
        except NotFoundError:
            raise DatasetNotFound(f"no dataset named {name!r}") from None
        return found.description or "", list(found.items)

    def _save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT]
    ) -> str:
        created = self.client.create_dataset(
            name=dataset.name,
            description=dataset.description,
            metadata={
                _EVALR: {
                    "input_type": dataset.input_type.__name__,
                    "verdict_type": dataset.verdict_type.__name__,
                }
            },
        )
        _, current = self._items(dataset.name, None)
        existing = {item.id: item for item in current if item.status == DatasetStatus.ACTIVE}
        kept: list[datetime] = []
        archived: list[datetime] = []
        wrote = False
        for example in dataset:
            fields = _fields(example)
            known = existing.pop(item_id(dataset.name, example.id), None)
            if known is not None and _same(known, fields):
                kept.append(known.updated_at)
                continue
            if known is not None and known.source_trace_id and example.trace_id is None:
                # Writing no source trace keeps the item's, so the item is made anew.
                self.client.api.dataset_items.delete(id=known.id)
            written = self.client.create_dataset_item(
                dataset_name=dataset.name,
                id=item_id(dataset.name, example.id),
                status=DatasetStatus.ACTIVE,
                **fields,
            )
            kept.append(written.updated_at)
            wrote = True
        for item in existing.values():
            gone = self.client.create_dataset_item(
                dataset_name=dataset.name,
                id=item.id,
                input=item.input,
                expected_output=item.expected_output,
                metadata=item.metadata,
                source_trace_id=item.source_trace_id,
                status=DatasetStatus.ARCHIVED,
            )
            archived.append(gone.updated_at)
        if wrote or not kept:
            return max([*kept, *archived], default=created.updated_at).isoformat()
        ids = {item_id(dataset.name, example.id) for example in dataset}
        return self._settled(dataset.name, ids, max(kept), created.updated_at).isoformat()

    def _settled(self, name: str, ids: set[str], latest: datetime, now: datetime) -> datetime:
        """The revision of a dataset this save wrote no example of.

        That is the time its examples were last written, unless an item the dataset held then
        has been archived since: Langfuse lists no archived item at any time after its archive,
        but still has the archive's time. An item deleted since has no time left, so the
        revision is ``now``.
        """
        _, then = self._items(name, latest)
        changes = [latest]
        for gone in {item.id for item in then if item.status == DatasetStatus.ACTIVE} - ids:
            try:
                changes.append(self.client.api.dataset_items.get(id=gone).updated_at)
            except NotFoundError:
                changes.append(now)
        return max(changes)


def _fields[InputT: BaseModel, VerdictT: BaseModel](
    example: Example[InputT, VerdictT],
) -> dict[str, Any]:
    record = example.model_dump(mode="json")
    return {
        "input": record["input"],
        "expected_output": {"verdict": record["verdict"], "reference": record["reference"]},
        "metadata": {**record["metadata"], _EVALR: {"example_id": example.id}},
        "source_trace_id": example.trace_id,
    }


def _same(item: DatasetItem, fields: dict[str, Any]) -> bool:
    return {
        "input": item.input,
        "expected_output": item.expected_output,
        "metadata": item.metadata,
        "source_trace_id": item.source_trace_id,
    } == fields


def _record(item: DatasetItem) -> dict[str, JsonValue]:
    """An item as an example's JSON record."""
    metadata = _object(item.metadata) or {}
    ours = _object(metadata.pop(_EVALR, None))
    output = _object(item.expected_output)
    if ours is not None and output is not None:
        return {
            "id": ours.get("example_id", item.id),
            "input": item.input,
            "verdict": output.get("verdict"),
            "reference": output.get("reference"),
            "trace_id": item.source_trace_id,
            "metadata": metadata,
        }
    return {
        "id": item.id,
        "input": item.input,
        "verdict": item.expected_output,
        "trace_id": item.source_trace_id,
        "metadata": metadata,
    }


def _object(value: object) -> dict[str, Any] | None:
    """A JSON object from Langfuse as a dict, or ``None`` if it is not an object."""
    return dict(cast(dict[str, Any], value)) if isinstance(value, dict) else None
