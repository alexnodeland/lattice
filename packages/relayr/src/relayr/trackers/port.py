"""The tracker port: one tenant's tracker workspace, in the port's own vocabulary.

An adapter speaks one tracker's REST and knows nothing of ledgers, runs or chains: Plane's in
`relayr.plane`, Vikunja's in `relayr.vikunja`, and an in-memory one in
[`relayr.trackers.FakeTracker`][relayr.trackers.FakeTracker]. Every adapter passes the one
contract test, `tests/trackers/test_contract.py`.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

type ProjectId = str
"""A project in the tracker, by the tracker's own id."""

type ItemKey = str
"""What lattice files an item by: Plane's external id, or Vikunja's marker."""

type CommentKey = str
"""What lattice posts a comment by, as an item's key."""

type State = Literal["backlog", "todo", "started", "done", "cancelled"]
"""Where an item is. Plane's state groups map one to one, `unstarted` as `todo`; Vikunja's
`done` flag reads as `done` or `todo`, and only `done` and `cancelled` set it."""

type Priority = Literal["none", "low", "medium", "high", "urgent"]
"""How urgent an item is."""


class ItemRef(BaseModel):
    """An item in a tracker project: enough to read it, change it and link to it."""

    model_config = ConfigDict(frozen=True)

    project: ProjectId
    id: str
    """The tracker's id for the item."""

    number: int
    """The item's number in its project."""

    name: str
    """What people call it, as the tracker shows it: `OPS-12`."""

    key: ItemKey | None = None
    """The key lattice filed it by, or None if lattice didn't."""


class CommentRef(BaseModel):
    """A comment on an item."""

    model_config = ConfigDict(frozen=True)

    item: str
    """The item's id."""

    id: str
    """The tracker's id for the comment."""


class ItemDraft(BaseModel):
    """What a rule files: its title and body, and what it leaves unset takes the binding's."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str = ""
    """The item's body, as HTML, which both trackers keep."""

    state: State | None = None
    """Where it starts; by default the binding's, or the tracker's default state."""

    priority: Priority | None = None
    """How urgent it is; by default the binding's, or `none`."""

    labels: tuple[str, ...] = ()
    """Label names, beside the binding's. Each is found or created by name."""


class ItemFields(BaseModel):
    """The fields a change sets; those left None are left as they are."""

    model_config = ConfigDict(frozen=True)

    title: str | None = None
    description: str | None = None
    state: State | None = None
    priority: Priority | None = None
    labels: tuple[str, ...] | None = None


class Item(BaseModel):
    """A snapshot of an item."""

    model_config = ConfigDict(frozen=True)

    ref: ItemRef
    title: str
    description: str
    """Its body as HTML, without Vikunja's marker."""

    state: State
    priority: Priority
    labels: tuple[str, ...]
    """Label names, sorted."""

    assignees: tuple[str, ...]
    """The tracker's ids for the people it is assigned to, sorted."""

    updated_at: datetime
    updated_by: str | None = None
    """The tracker's id for whoever changed it last, if the tracker says."""


class Comment(BaseModel):
    """A comment on an item."""

    model_config = ConfigDict(frozen=True)

    ref: CommentRef
    body: str
    """Its text as HTML, without Vikunja's marker."""

    author: str | None
    """The tracker's id for whoever wrote it, if the tracker says."""

    created_at: datetime
    key: CommentKey | None = None
    """The key lattice posted it by, or None if lattice didn't."""


class Cursor(BaseModel):
    """Where a read of a project's items stopped: the last item's `updated_at`, then id."""

    model_config = ConfigDict(frozen=True)

    updated_at: datetime
    id: str


class Page[T](BaseModel):
    """What a read found after a cursor, oldest first, and the cursor after it."""

    model_config = ConfigDict(frozen=True)

    items: tuple[T, ...]
    next: Cursor | None
    """The cursor after the last item; None if there was none."""


class Nudge(BaseModel):
    """A verified webhook's news: a project changed, so poll it now."""

    model_config = ConfigDict(frozen=True)

    project: ProjectId


class TrackerCredentials(BaseModel):
    """How to reach one tenant's tracker workspace. Never logged, recorded or traced."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    """The tracker's URL, such as `https://plane.example.com`."""

    api_key: str = Field(repr=False)
    """The key of the tenant's own tracker user."""

    webhook_secret: str = Field(repr=False)
    """What the tracker signs its webhooks with."""

    workspace: str = ""
    """The tenant's workspace slug, on Plane."""


class TrackerError(Exception):
    """A tracker refused or failed a request."""


class RateLimited(TrackerError):
    """The tracker's rate limit is reached; try again after `retry_after` seconds, if it says."""

    def __init__(self, retry_after: float | None) -> None:
        super().__init__(f"rate limited; retry after {retry_after}s")
        self.retry_after = retry_after


class Unavailable(TrackerError):
    """The tracker didn't answer, or failed: a request may or may not have taken effect."""


class NotFound(TrackerError):
    """What a request named isn't there."""


class Refused(TrackerError):
    """The tracker refused a request as invalid, for `reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Unauthorized(TrackerError):
    """The tracker refused the key."""


class Tracker(Protocol):
    """One tenant's tracker workspace, as one of the tenant's lattice workspaces writes to it.

    An adapter is made from the tenant's credentials and a source,
    `lattice:<tenant>/<workspace>`, which tells its keys from another lattice workspace's. Every
    method raises a [`TrackerError`][relayr.trackers.TrackerError] when the tracker refuses or
    fails a request.
    """

    async def find(self, project: ProjectId, key: ItemKey) -> ItemRef | None:
        """Return the item lattice filed in a project by a key, or None if there is none."""
        ...

    async def create(self, project: ProjectId, key: ItemKey, draft: ItemDraft) -> ItemRef:
        """File an item by a key, with the draft's values; labels are found or created by name.

        Plane returns an item its external ids already name, rather than making another.
        """
        ...

    async def item(self, ref: ItemRef) -> Item | None:
        """Return an item's snapshot, or None if it was deleted; an archived item is returned."""
        ...

    async def update(self, ref: ItemRef, fields: ItemFields) -> None:
        """Set the fields given on an item."""
        ...

    async def comment(self, ref: ItemRef, key: CommentKey, body: str) -> CommentRef:
        """Post a comment on an item by a key, or return the one the key already posted."""
        ...

    async def items(self, project: ProjectId, after: Cursor | None) -> Page[Item]:
        """Return a project's items changed after a cursor, by `updated_at` then id, oldest first.

        It reads what the tracker lists, which on Plane leaves out archived, draft and triage
        items.
        """
        ...

    async def comments(self, ref: ItemRef, after: CommentRef | None) -> list[Comment]:
        """Return an item's comments after one, oldest first, or all of them."""
        ...

    def nudge(self, headers: Mapping[str, str], body: bytes) -> Nudge | None:
        """Verify a webhook against the tenant's secret, and say which project to poll.

        Returns None for anything it can't verify.
        """
        ...

    def link(self, ref: ItemRef) -> str:
        """Return the item's address in the tracker's web app."""
        ...

    def holds(self, state: State) -> State:
        """Return the state an item set to `state` reads back as.

        Plane holds every state; Vikunja's `done` flag holds two of the five.
        """
        ...
