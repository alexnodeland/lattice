"""The test application's own types: the events its projections publish, and an artifact."""

from artifactr import MarkdownArtifact
from reflexr import Event


class AppEvent(Event, abstract=True, event_namespace="app"):
    """The test application's namespace."""


class Deployed(AppEvent, name="deployed"):
    service: str


class TimelineChanged(AppEvent, name="timeline_changed"):
    entries: int


class Note(MarkdownArtifact, name="note"):
    """A Markdown note."""
