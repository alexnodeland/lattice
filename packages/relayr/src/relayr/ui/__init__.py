"""What a person sends reaches reflexr's rules as one event, whichever way it was asked.

The ``forms`` extra, for an application with artifactr's forms and dashboards (``artifactr.ui``,
``artifactr-ai[forms]``). relayr's follower bridges artifactr's log into reflexr; give reflexr
:data:`UI_EVENTS` and :data:`UI_PUBLISHERS` beside the ``artifactr`` reservation, and the
follower :data:`UI_PROJECTIONS`::

    automation = reflexr.Workspaces(
        storage,
        events=[*BRIDGED, *UI_EVENTS, *app_events],
        publishers={"artifactr": [SOURCE], **UI_PUBLISHERS},
    )
    followers = Followers(
        collaboration, automation, ledger, projections=Projections(**UI_PROJECTIONS)
    )

An answer to ``ask_form`` and a ``submission`` to a form both become ``ui:form_submitted``, so a
rule is written once for both ways of asking; a submission to an app becomes
``ui:app_submitted``. A submission's ``artifact_changed`` and ``artifact_archived`` become
nothing. ``ui:`` is reserved to the follower's publisher, so no client publishes a submission
itself (ADR-0036).
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Self, TypedDict, cast

from pydantic import JsonValue, model_validator

from artifactr.core import (
    Actor,
    ArtifactCreated,
    ArtifactId,
    DeferredAnswered,
    Envelope,
    RunId,
    ThreadId,
)
from artifactr.ui import ASK_FORM, Submission
from reflexr import Event, SourceActor
from relayr.events import Projection

__all__ = [
    "UI_EVENTS",
    "UI_PROJECTIONS",
    "UI_PUBLISHERS",
    "AppSubmitted",
    "FormSubmitted",
    "UiEvent",
    "UiProjections",
]


class UiEvent(Event, abstract=True, event_namespace="ui"):
    """The base of the forms' events: who sent what, and where."""

    author: Actor
    """Who sent it in artifactr: the envelope's actor there."""

    thread_id: ThreadId | None = None
    """The thread it was sent in, if any."""

    values: dict[str, JsonValue]
    """The values sent: to a form, checked against its schema before they were recorded."""


class FormSubmitted(UiEvent, name="form_submitted"):
    """A form was sent: a ``submission`` to a form artifact, or the answer to ``ask_form``.

    A submission carries ``form_id`` and ``version``; an answer, the ``turn_id`` that asked and
    its ``tool_call_id``.
    """

    form_id: ArtifactId | None = None
    version: int | None = None
    turn_id: RunId | None = None
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        submitted = self.form_id is not None and self.version is not None
        answered = self.turn_id is not None and self.tool_call_id is not None
        named = (self.form_id, self.version, self.turn_id, self.tool_call_id)
        if submitted == answered or sum(field is not None for field in named) != 2:
            raise ValueError("a form is sent as a submission or as an answer, and only one")
        return self


class AppSubmitted(UiEvent, name="app_submitted"):
    """A ``submission`` to an app, against the version of it the person saw."""

    app_id: ArtifactId
    version: int


UI_EVENTS: Final[tuple[type[UiEvent], ...]] = (FormSubmitted, AppSubmitted)
"""The forms' event types, for reflexr's ``Workspaces(events=...)``."""

UI_PUBLISHERS: Final[Mapping[str, tuple[SourceActor, ...]]] = MappingProxyType(
    {"ui": (SourceActor(name="artifactr"),)}
)
"""The ``ui`` namespace, reserved to relayr's follower, for reflexr's ``publishers=``."""


class _Origin(TypedDict):
    """The fields every event of a submission takes from its envelope and its data."""

    author: Actor
    thread_id: ThreadId | None
    values: dict[str, JsonValue]


def _answered(envelope: Envelope) -> FormSubmitted:
    """An answer to ``ask_form``: its values, which the check found to fit."""
    event = cast("DeferredAnswered", envelope.event)
    return FormSubmitted(
        author=envelope.actor,
        thread_id=event.thread_id,
        values=cast("dict[str, JsonValue]", event.answer),
        turn_id=event.run_id,
        tool_call_id=event.tool_call_id,
    )


def _submitted(envelope: Envelope) -> UiEvent | None:
    """A submission's creation, as what it answers; its later events, as nothing."""
    if not isinstance(envelope.event, ArtifactCreated):
        return None
    submission = Submission.model_validate(envelope.event.data)
    origin = _Origin(author=envelope.actor, thread_id=envelope.thread_id, values=submission.values)
    if submission.form_id is not None:
        return FormSubmitted(**origin, form_id=submission.form_id, version=submission.version)
    return AppSubmitted(**origin, app_id=cast("str", submission.app_id), version=submission.version)


class UiProjections(TypedDict):
    """The projections relayr's ``Projections`` takes, by its argument's name."""

    artifacts: Mapping[str, Projection]
    deferred: Mapping[str, Projection]


UI_PROJECTIONS: Final = UiProjections(
    artifacts=MappingProxyType({Submission.kind: _submitted}),
    deferred=MappingProxyType({ASK_FORM: _answered}),
)
"""The forms' projections, by the argument of relayr's ``Projections`` each is for:
``Projections(**UI_PROJECTIONS)``, or each merged with the application's own of that name."""
