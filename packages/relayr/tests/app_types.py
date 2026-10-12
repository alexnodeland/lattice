"""The test application's own types: the events its projections publish, and an artifact."""

from typing import Self

from pydantic import model_validator

from artifactr import Artifact, MarkdownArtifact
from reflexr import Event


class AppEvent(Event, abstract=True, event_namespace="app"):
    """The test application's namespace."""


class Deployed(AppEvent, name="deployed"):
    service: str


class TimelineChanged(AppEvent, name="timeline_changed"):
    entries: int


class Note(MarkdownArtifact, name="note"):
    """A Markdown note."""


class Range(Artifact, name="range"):
    """Two bounds, the low below the high: valid or not as a whole."""

    low: int = 0
    high: int = 10

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.low >= self.high:
            raise ValueError("low must be below high")
        return self
