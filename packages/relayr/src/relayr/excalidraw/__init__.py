"""A diagram's changes reach reflexr's rules as which elements were added, changed and removed.

The ``excalidraw`` extra, for an application with artifactr's diagrams (``artifactr.excalidraw``,
``artifactr-ai[excalidraw]``). relayr's follower bridges artifactr's log into reflexr; give
reflexr :data:`EXCALIDRAW_EVENTS` and :data:`EXCALIDRAW_PUBLISHERS` beside the ``artifactr``
reservation, and the follower :data:`EXCALIDRAW_PROJECTIONS` (lattice RFC-0006, relayr
ADR-0041)::

    automation = reflexr.Workspaces(
        storage,
        events=[*BRIDGED, *EXCALIDRAW_EVENTS, *app_events],
        publishers={"artifactr": [SOURCE], **EXCALIDRAW_PUBLISHERS},
    )
    followers = Followers(
        collaboration, automation, ledger, projections=Projections(**EXCALIDRAW_PROJECTIONS)
    )

Each commit to a diagram's elements, a person's save, an agent's accepted proposal or the sweep,
becomes one ``excalidraw:elements_changed``: the ids of the elements it added, changed and
removed, each with its label where the commit says one, bounded at :data:`MAX_LABEL`. A commit
that touches no element, an image's file alone, bridges nothing. An element marked deleted is
removed, as the canvas shows it; the sweep's removal of a tombstone is removed too. Its creation
becomes one as well, every element added. Its archiving, and a patch that isn't element-scoped,
such as a rename's text edits, are bridged as the default set's. ``excalidraw:`` is reserved to the
follower's publisher, so no client publishes a diagram's changes itself. A comment on an element
is feedback (``diagram_comment``), bridged as the default set's ``artifactr:feedback_given``, its
``element_id`` in its value.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, TypedDict

from pydantic import BaseModel, ConfigDict, JsonValue

from artifactr.core import (
    Actor,
    ArtifactChanged,
    ArtifactCreated,
    ArtifactId,
    Envelope,
    JsonPatch,
    ProposalId,
    RunId,
    ThreadId,
)
from artifactr.excalidraw import Diagram
from reflexr import Event, SourceActor
from relayr.events import Projection, Projections

__all__ = [
    "EXCALIDRAW_EVENTS",
    "EXCALIDRAW_PROJECTIONS",
    "EXCALIDRAW_PUBLISHERS",
    "MAX_LABEL",
    "ElementTouched",
    "ElementsChanged",
    "ExcalidrawEvent",
    "ExcalidrawProjections",
]


class ElementTouched(BaseModel):
    """An element a commit touched: its id, and its label where the commit says one."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str | None = None
    """Its text, for a text; a container's, from the text bound in it; its name, for a frame."""


class ExcalidrawEvent(Event, abstract=True, event_namespace="excalidraw"):
    """The base of the diagrams' events: who acted, and where."""

    author: Actor
    """Who committed it in artifactr: the envelope's actor there."""

    thread_id: ThreadId | None = None
    turn_id: RunId | None = None


class ElementsChanged(ExcalidrawEvent, name="elements_changed"):
    """One commit to a diagram: the elements it added, changed and removed."""

    diagram_id: ArtifactId
    version: int
    summary: str | None = None
    proposal_id: ProposalId | None = None
    """The proposal whose acceptance made the commit, if one did."""
    added: tuple[ElementTouched, ...] = ()
    changed: tuple[ElementTouched, ...] = ()
    removed: tuple[ElementTouched, ...] = ()


EXCALIDRAW_EVENTS: Final[tuple[type[ElementsChanged], ...]] = (ElementsChanged,)
"""The diagrams' event types, for reflexr's ``Workspaces(events=...)``."""

EXCALIDRAW_PUBLISHERS: Final[Mapping[str, tuple[SourceActor, ...]]] = MappingProxyType(
    {"excalidraw": (SourceActor(name="artifactr"),)}
)
"""The ``excalidraw`` namespace, reserved to relayr's follower, for reflexr's ``publishers=``."""


MAX_LABEL: Final = 200
"""The most characters of an element's label an event carries, its ellipsis included: an
element's text leaves the diagram into reflexr's log, rules' values and what they send on."""


def _bounded(text: str) -> str:
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1] + "\u2026"


def _labels(elements: Mapping[str, JsonValue]) -> dict[str, str]:
    """Each element's label, as what a commit holds of it says, each bounded.

    A text's is its own; a container's is the text bound in it; any other's is its name. The
    text bound in a container wins over the container's name, whatever their order.
    """
    named: dict[str, str] = {}
    bound: dict[str, str] = {}
    for key, element in elements.items():
        if not isinstance(element, dict):
            continue
        text, name = element.get("text"), element.get("name")
        if element.get("type") == "text" and isinstance(text, str) and text:
            bound[key] = text
            container = element.get("containerId")
            if isinstance(container, str):
                bound[container] = text
        elif isinstance(name, str) and name:
            named[key] = name
    return {key: _bounded(label) for key, label in {**named, **bound}.items()}


def _touched(keys: list[str], labels: Mapping[str, str]) -> tuple[ElementTouched, ...]:
    return tuple(ElementTouched(id=key, label=labels.get(key)) for key in keys)


def _changes(patch: JsonPatch) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    """What a diagram's element-scoped patch added, changed and removed, in its order.

    An element is named once, by the last op on it: a patch the checks let through touches
    each element once, but a reader keeps to one id a list either way.
    """
    last: dict[str, str] = {}
    values: dict[str, JsonValue] = {}
    for op in patch.ops:
        # Core has applied the patch, so each op has its path; an odd one is passed over.
        path = op.get("path")
        key = path.removeprefix("/elements/") if isinstance(path, str) else ""
        if not path or key == path or not key or "/" in key:
            continue  # a test of a version, an image's file, or not an element at all
        kind, value = op.get("op"), op.get("value")
        values[key] = value
        deleted = isinstance(value, dict) and value.get("isDeleted") is True
        if kind == "remove" or (kind == "replace" and deleted):
            last[key] = "removed"
        elif kind == "add":
            last[key] = "added"
        elif kind == "replace":
            last[key] = "changed"
    sorted_by = {
        what: [key for key, was in last.items() if was == what]
        for what in ("added", "changed", "removed")
    }
    return sorted_by["added"], sorted_by["changed"], sorted_by["removed"], _labels(values)


class _Origin(TypedDict):
    """The fields every diagram's event takes from its envelope."""

    author: Actor
    thread_id: ThreadId | None
    turn_id: RunId | None


_BY_DEFAULT: Final = Projections()
"""The default set, for what a diagram's projection leaves as it is: its archiving, and a patch
that isn't element-scoped."""


def _changed(envelope: Envelope) -> Event | None:
    """A diagram's creation or a commit to its elements, as its elements changed.

    A commit that touches no element, an image's file alone, bridges nothing: rules on a diagram
    are rules on its elements. Archiving, and a patch that isn't element-scoped, such as a
    rename's text edits, are bridged as the default set's.
    """
    origin = _Origin(author=envelope.actor, thread_id=envelope.thread_id, turn_id=envelope.run_id)
    event = envelope.event
    if isinstance(event, ArtifactCreated):
        held = event.data.get("elements")
        elements = held if isinstance(held, dict) else {}
        live = [
            key
            for key, element in elements.items()
            if isinstance(element, dict) and element.get("isDeleted") is not True
        ]
        return ElementsChanged(
            **origin,
            diagram_id=event.artifact_id,
            version=event.version,
            proposal_id=event.proposal_id,
            added=_touched(live, _labels(elements)),
        )
    if isinstance(event, ArtifactChanged) and isinstance(event.patch, JsonPatch):
        added, changed, removed, labels = _changes(event.patch)
        if not (added or changed or removed):
            return None
        return ElementsChanged(
            **origin,
            diagram_id=event.artifact_id,
            version=event.version,
            summary=event.summary,
            proposal_id=event.proposal_id,
            added=_touched(added, labels),
            changed=_touched(changed, labels),
            removed=_touched(removed, labels),
        )
    return _BY_DEFAULT.project(envelope)


class ExcalidrawProjections(TypedDict):
    """The projections relayr's ``Projections`` takes, by its argument's name."""

    artifacts: Mapping[str, Projection]


EXCALIDRAW_PROJECTIONS: Final = ExcalidrawProjections(
    artifacts=MappingProxyType({Diagram.kind: _changed}),
)
"""The diagrams' projections: ``Projections(**EXCALIDRAW_PROJECTIONS)``, or merged with the
application's own ``artifacts``."""
