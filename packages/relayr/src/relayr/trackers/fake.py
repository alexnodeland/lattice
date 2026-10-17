"""A tracker in memory, for tests: one workspace's projects, items and comments.

It keeps the port's promises as the trackers do: an archived item is read but not listed, a
deleted one is gone, and a second item filed by a key is made, as Vikunja makes it, unless the
fake dedupes, as Plane does. Tests act in it as
people do, and make it fail as a tracker does.
"""

import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from relayr.ledger import Clock, utc_now
from relayr.trackers.port import (
    Comment,
    CommentKey,
    CommentRef,
    Cursor,
    Item,
    ItemDraft,
    ItemFields,
    ItemKey,
    ItemRef,
    NotFound,
    Nudge,
    Page,
    Priority,
    ProjectId,
    State,
    TrackerCredentials,
    TrackerError,
    Unauthorized,
    Unavailable,
)
from relayr.trackers.signatures import signed

SIGNATURE = "x-fake-signature"
"""The header a nudge's signature is in: HMAC-SHA256, hex, over the body."""

PERSON = "person"
"""Who a test's changes are by, unless it names someone."""

type _Key = tuple[str, str]
"""What lattice filed something by: its source and its key."""


@dataclass
class _Comment:
    ref: CommentRef
    body: str
    author: str
    created_at: datetime
    key: _Key | None


@dataclass
class _Item:
    project: ProjectId
    id: str
    number: int
    title: str
    description: str
    state: State
    priority: Priority
    labels: set[str]
    updated_at: datetime
    updated_by: str
    key: _Key | None
    archived: bool = False
    comments: list[_Comment] = field(default_factory=list[_Comment])


@dataclass
class _Store:
    """The workspace's state, which the tracker and its connections share."""

    api_key: str
    clock: Clock
    dedupes: bool
    items: dict[str, _Item] = field(default_factory=dict[str, _Item])
    failures: list[TrackerError | None] = field(default_factory=list[TrackerError | None])
    lose_created: bool = False
    created: int = 0

    def request(self, credentials: TrackerCredentials) -> None:
        """Answer a request: with the next failure, if a test set one, or by its key."""
        failure = self.failures.pop(0) if self.failures else None
        if failure is not None:
            raise failure
        if not hmac.compare_digest(credentials.api_key, self.api_key):
            raise Unauthorized("the key isn't the tracker's")

    def existing(self, item_id: str) -> _Item:
        found = self.items.get(item_id)
        if found is None:
            raise NotFound(f"no item {item_id}")
        return found

    def add(self, project: ProjectId, key: _Key | None, draft: ItemDraft, by: str) -> _Item:
        self.created += 1
        number = 1 + sum(item.project == project for item in self.items.values())
        item = _Item(
            project=project,
            id=f"item-{self.created}",
            number=number,
            title=draft.title,
            description=draft.description,
            state=draft.state or "backlog",
            priority=draft.priority or "none",
            labels=set(draft.labels),
            updated_at=self.clock(),
            updated_by=by,
            key=key,
        )
        self.items[item.id] = item
        return item

    def change(self, item: _Item, fields: ItemFields, by: str) -> None:
        for name, value in fields.model_dump(exclude_none=True).items():
            setattr(item, name, set(value) if name == "labels" else value)
        item.updated_at, item.updated_by = self.clock(), by

    def comment(self, item: _Item, key: _Key | None, body: str, by: str) -> _Comment:
        ref = CommentRef(item=item.id, id=f"{item.id}-comment-{len(item.comments) + 1}")
        comment = _Comment(ref=ref, body=body, author=by, created_at=self.clock(), key=key)
        item.comments.append(comment)
        return comment


class FakeTracker:
    """A tracker workspace in memory. Give `connect` to [`Trackers`][relayr.trackers.Trackers].

    Args:
        api_key: The key it accepts; a request with another is `Unauthorized`.
        dedupes: Whether a create by a key already used returns its item, as Plane's 409 does,
            rather than filing another, as Vikunja does.
        clock: Returns the current time, which items are updated at.
    """

    def __init__(
        self, *, api_key: str = "key", dedupes: bool = False, clock: Clock = utc_now
    ) -> None:
        self._store = _Store(api_key=api_key, clock=clock, dedupes=dedupes)

    def connect(self, credentials: TrackerCredentials, source: str) -> "FakeConnection":
        """Connect as a lattice workspace's adapter does, with the tenant's credentials."""
        return FakeConnection(self._store, credentials, source)

    @property
    def created(self) -> int:
        """How many items were filed, by lattice and by people."""
        return self._store.created

    def rotate(self, api_key: str) -> None:
        """Accept another key, and refuse the one before."""
        self._store.api_key = api_key

    def fail(self, *errors: TrackerError | None) -> None:
        """Fail the next requests, one error each; None lets one through."""
        self._store.failures.extend(errors)

    def lose_next_created(self) -> None:
        """Make the next item lattice files, and lose the answer, as `Unavailable`."""
        self._store.lose_created = True

    def add(self, project: ProjectId, title: str, *, by: str = PERSON) -> ItemRef:
        """File an item, as a person does, with no key."""
        return _ref(self._store.add(project, None, ItemDraft(title=title), by))

    def edit(self, ref: ItemRef, fields: ItemFields, *, by: str = PERSON) -> None:
        """Change an item, as a person does."""
        self._store.change(self._store.existing(ref.id), fields, by)

    def reply(self, ref: ItemRef, body: str, *, by: str = PERSON) -> CommentRef:
        """Comment on an item, as a person does."""
        return self._store.comment(self._store.existing(ref.id), None, body, by).ref

    def archive(self, ref: ItemRef) -> None:
        """Archive an item: it is read, but no longer listed."""
        self._store.existing(ref.id).archived = True

    def delete(self, ref: ItemRef) -> None:
        """Delete an item, as a person does: its key files again."""
        del self._store.items[ref.id]

    def items_in(self, project: ProjectId) -> list[Item]:
        """Every item in a project, archived ones included, in the order they were filed."""
        return [_item(item, None) for item in self._store.items.values() if item.project == project]


class FakeConnection:
    """A lattice workspace's adapter to a [`FakeTracker`][relayr.trackers.FakeTracker]."""

    def __init__(self, store: _Store, credentials: TrackerCredentials, source: str) -> None:
        self._store = store
        self._credentials = credentials
        self._source = source
        self.user = f"relayr:{source}"
        """Who its writes are by."""

    async def find(self, project: ProjectId, key: ItemKey) -> ItemRef | None:
        """Return the item lattice filed in a project by a key, or None if there is none."""
        found = self._filed(project, key)
        return None if found is None else _ref(found, self._source)

    async def create(self, project: ProjectId, key: ItemKey, draft: ItemDraft) -> ItemRef:
        """File an item by a key; or, if the tracker dedupes, return the one the key filed."""
        self._store.request(self._credentials)
        found = self._match(project, key) if self._store.dedupes else None
        if found is None:
            found = self._store.add(project, (self._source, key), draft, self.user)
            if self._store.lose_created:
                self._store.lose_created = False
                raise Unavailable("the tracker filed the item, and its answer was lost")
        return _ref(found, self._source)

    async def item(self, ref: ItemRef) -> Item | None:
        """Return an item's snapshot, archived or not, or None if it was deleted."""
        self._store.request(self._credentials)
        found = self._store.items.get(ref.id)
        return None if found is None else _item(found, self._source)

    async def update(self, ref: ItemRef, fields: ItemFields) -> None:
        """Set the fields given on an item."""
        self._store.request(self._credentials)
        self._store.change(self._store.existing(ref.id), fields, self.user)

    async def comment(self, ref: ItemRef, key: CommentKey, body: str) -> CommentRef:
        """Post a comment by a key, or return the one the key already posted."""
        self._store.request(self._credentials)
        item = self._store.existing(ref.id)
        for comment in item.comments:
            if comment.key == (self._source, key):
                return comment.ref
        return self._store.comment(item, (self._source, key), body, self.user).ref

    async def items(self, project: ProjectId, after: Cursor | None) -> Page[Item]:
        """Return a project's listed items changed after a cursor, oldest first."""
        self._store.request(self._credentials)
        listed = [
            _item(item, self._source)
            for item in self._store.items.values()
            if item.project == project and not item.archived
        ]
        listed.sort(key=lambda item: (item.updated_at, item.ref.id))
        if after is not None:
            listed = [i for i in listed if (i.updated_at, i.ref.id) > (after.updated_at, after.id)]
        last = Cursor(updated_at=listed[-1].updated_at, id=listed[-1].ref.id) if listed else after
        return Page(items=tuple(listed), next=last)

    async def comments(self, ref: ItemRef, after: CommentRef | None) -> list[Comment]:
        """Return an item's comments after one, oldest first, or all of them."""
        self._store.request(self._credentials)
        comments = [self._read(comment) for comment in self._store.existing(ref.id).comments]
        ids = [comment.ref.id for comment in comments]
        return (
            comments[ids.index(after.id) + 1 :]
            if after is not None and after.id in ids
            else comments
        )

    def nudge(self, headers: Mapping[str, str], body: bytes) -> Nudge | None:
        """Verify a nudge's signature, and say which project to poll."""
        if not signed(headers, body, self._credentials.webhook_secret.encode(), SIGNATURE):
            return None
        try:
            return Nudge.model_validate_json(body)
        except ValidationError:
            return None

    def link(self, ref: ItemRef) -> str:
        """Return the item's address."""
        return f"{self._credentials.base_url}/{ref.project}/{ref.number}"

    def _filed(self, project: ProjectId, key: ItemKey) -> _Item | None:
        self._store.request(self._credentials)
        return self._match(project, key)

    def _match(self, project: ProjectId, key: ItemKey) -> _Item | None:
        for item in self._store.items.values():
            if item.project == project and item.key == (self._source, key):
                return item
        return None

    def _read(self, comment: _Comment) -> Comment:
        return Comment(
            ref=comment.ref,
            body=comment.body,
            author=comment.author,
            created_at=comment.created_at,
            key=_own(comment.key, self._source),
        )


def _own(key: _Key | None, source: str | None) -> str | None:
    """A key as a source reads it: its own keys, and nobody else's."""
    return key[1] if key is not None and key[0] == source else None


def _ref(item: _Item, source: str | None = None) -> ItemRef:
    return ItemRef(
        project=item.project,
        id=item.id,
        number=item.number,
        name=f"{item.project.upper()}-{item.number}",
        key=_own(item.key, source),
    )


def _item(item: _Item, source: str | None) -> Item:
    return Item(
        ref=_ref(item, source),
        title=item.title,
        description=item.description,
        state=item.state,
        priority=item.priority,
        labels=tuple(sorted(item.labels)),
        assignees=(),
        updated_at=item.updated_at,
        updated_by=item.updated_by,
    )
