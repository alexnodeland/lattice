"""Vikunja's REST API (v2.7), as the tracker port.

Vikunja keeps no external ids, so an item or comment lattice writes ends with a marker,
`<p>lattice-key: <source>/<key></p>`, which `find` searches for within the bound project. Its
`POST /tasks/{id}` sets every field, zeroing those left out, so a change reads the task first and
sends it whole. Labels are added and removed one at a time, which moves the task's `updated`;
setting them in bulk doesn't.
"""

import re
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from html import escape, unescape
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from relayr.trackers import (
    Comment,
    CommentKey,
    CommentRef,
    Connect,
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
)
from relayr.trackers.http import Api
from relayr.trackers.signatures import signed

SIGNATURE: Final = "x-vikunja-signature"
"""The header Vikunja signs a webhook in: HMAC-SHA256, hex, over the bytes it sends."""

INTEGRATION: Final = "tracker:vikunja"
"""Vikunja's key among the application's integrations (`relayr.integrations`)."""

PER_PAGE: Final = 50
"""Vikunja's default and largest page."""

_PRIORITIES: Final[dict[Priority, int]] = {"none": 0, "low": 1, "medium": 2, "high": 3, "urgent": 4}
"""Vikunja's priorities by the port's; its 5, "DO NOW", reads as `urgent`."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _User(_Model):
    id: int


class _Label(_Model):
    id: int
    title: str


class _Task(_Model):
    id: int
    project_id: int
    index: int
    identifier: str
    title: str
    description: str
    done: bool
    priority: int
    labels: tuple[_Label, ...] | None
    assignees: tuple[_User, ...] | None
    updated: datetime


class _Comment(_Model):
    id: int
    comment: str
    author: _User | None
    created: datetime


class _Hook(_Model):
    class _Data(_Model):
        class _Project(_Model):
            id: int

        project: _Project

    data: _Data


_LABELS: Final = TypeAdapter[list[_Label] | None](list[_Label] | None)


class VikunjaTracker:
    """One tenant's Vikunja, as one lattice workspace writes to it.

    Args:
        credentials: The tenant's: Vikunja's URL, an API token of the tenant's own user with the
            scopes the tracker guide lists, and its webhooks' secret.
        source: The lattice workspace, `lattice:<tenant>/<workspace>`, which its markers name.
        client: The HTTP client, which the application shares and closes.
    """

    def __init__(
        self, credentials: TrackerCredentials, source: str, *, client: httpx.AsyncClient
    ) -> None:
        self._api = Api(
            client,
            f"{credentials.base_url.rstrip('/')}/api/v1",
            {"Authorization": f"Bearer {credentials.api_key}"},
        )
        self._base_url = credentials.base_url.rstrip("/")
        self._secret = credentials.webhook_secret.encode()
        self._source = source
        self._marked = re.compile(
            rf"<p>lattice-key: {re.escape(escape(source))}/(?P<key>[^<]*)</p>\s*\Z"
        )
        self._labels: dict[str, int] = {}

    async def find(self, project: ProjectId, key: ItemKey) -> ItemRef | None:
        """Return the item whose description ends with the key's marker, or None."""
        params = {"filter": f"project = {int(project)}", "s": self._marker(key)}
        async for task in self._tasks(params):
            if self._key(task.description) == key:
                return self._ref(task)
        return None

    async def create(self, project: ProjectId, key: ItemKey, draft: ItemDraft) -> ItemRef:
        """Make a task with the key's marker at the end of its description, then its labels."""
        task = {
            "title": draft.title,
            "description": f"{draft.description}<p>{self._marker(key)}</p>",
            "priority": _PRIORITIES[draft.priority or "none"],
            "done": _done(draft.state),
        }
        response = await self._api.request("PUT", f"/projects/{int(project)}/tasks", json=task)
        made = _Task.model_validate_json(response.content)
        await self._label(made, draft.labels)
        return self._ref(made)

    async def item(self, ref: ItemRef) -> Item | None:
        """Return a task's snapshot, or None if it was deleted."""
        try:
            task = await self._task(ref.id)
        except NotFound:
            return None
        return self._item(task)

    async def update(self, ref: ItemRef, fields: ItemFields) -> None:
        """Send the task whole with the fields given set, then add and remove labels."""
        sent = (await self._api.request("GET", f"/tasks/{int(ref.id)}")).json()
        task = _Task.model_validate(sent)
        if fields.title is not None:
            sent["title"] = fields.title
        if fields.description is not None:
            mark = "" if ref.key is None else f"<p>{self._marker(ref.key)}</p>"
            sent["description"] = f"{fields.description}{mark}"
        if fields.priority is not None:
            sent["priority"] = _PRIORITIES[fields.priority]
        if fields.state is not None:
            sent["done"] = _done(fields.state)
        await self._api.request("POST", f"/tasks/{task.id}", json=sent)
        if fields.labels is not None:
            await self._label(task, fields.labels)

    async def comment(self, ref: ItemRef, key: CommentKey, body: str) -> CommentRef:
        """Post a comment ending with the key's marker, unless one on the task has it."""
        for comment in await self._comments(ref):
            if self._key(comment.comment) == key:
                return CommentRef(item=ref.id, id=str(comment.id))
        marked = {"comment": f"{body}<p>{self._marker(key)}</p>"}
        response = await self._api.request("PUT", f"/tasks/{int(ref.id)}/comments", json=marked)
        return CommentRef(item=ref.id, id=str(_Comment.model_validate_json(response.content).id))

    async def items(self, project: ProjectId, after: Cursor | None) -> Page[Item]:
        """Return the project's tasks updated after a cursor, by `updated` then id.

        Vikunja keeps `updated` to the second, so the filter asks from the second before the
        cursor's, and what isn't after it is dropped here. Pages are read by id, which a change
        during the read doesn't reshuffle.
        """
        params: dict[str, Any] = {
            "filter": f"project = {int(project)}",
            "sort_by": "id",
            "order_by": "asc",
        }
        if after is not None:
            since = after.updated_at.astimezone(UTC).replace(microsecond=0) - timedelta(seconds=1)
            params["filter"] += f" && updated > {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        found = [self._item(task) async for task in self._tasks(params)]
        found.sort(key=_order)
        if after is not None:
            found = [item for item in found if _order(item) > (after.updated_at, int(after.id))]
        last = found[-1] if found else None
        return Page(
            items=tuple(found),
            next=after if last is None else Cursor(updated_at=last.updated_at, id=last.ref.id),
        )

    async def comments(self, ref: ItemRef, after: CommentRef | None) -> list[Comment]:
        """Return a task's comments after one, oldest first, or all of them."""
        found = [
            Comment(
                ref=CommentRef(item=ref.id, id=str(comment.id)),
                body=self._unmarked(comment.comment),
                author=None if comment.author is None else str(comment.author.id),
                created_at=comment.created,
                key=self._key(comment.comment),
            )
            for comment in await self._comments(ref)
        ]
        ids = [comment.ref.id for comment in found]
        return found[ids.index(after.id) + 1 :] if after is not None and after.id in ids else found

    def nudge(self, headers: Mapping[str, str], body: bytes) -> Nudge | None:
        """Verify a webhook's signature over its bytes, and return its project."""
        if not signed(headers, body, self._secret, SIGNATURE):
            return None
        try:
            hook = _Hook.model_validate_json(body)
        except ValidationError:
            return None
        return Nudge(project=str(hook.data.project.id))

    def link(self, ref: ItemRef) -> str:
        """Return the task's page: `<base>/tasks/<id>`."""
        return f"{self._base_url}/tasks/{ref.id}"

    # ─── how ──────────────────────────────────────────────────────────────────

    def _marker(self, key: str) -> str:
        return f"lattice-key: {escape(self._source)}/{escape(key)}"

    def _key(self, text: str) -> str | None:
        """The key a text's marker names, if it is this source's."""
        marked = self._marked.search(text)
        return None if marked is None else unescape(marked["key"])

    def _unmarked(self, text: str) -> str:
        return self._marked.sub("", text)

    async def _task(self, task_id: str) -> _Task:
        response = await self._api.request("GET", f"/tasks/{int(task_id)}")
        return _Task.model_validate_json(response.content)

    async def _tasks(self, params: Mapping[str, Any]) -> AsyncIterator[_Task]:
        async for page in self._pages("/tasks", params):
            for task in page:
                yield _Task.model_validate(task)

    async def _comments(self, ref: ItemRef) -> list[_Comment]:
        """A task's comments, oldest first: Vikunja lists them newest first."""
        found = [
            _Comment.model_validate(comment)
            async for page in self._pages(f"/tasks/{int(ref.id)}/comments", {})
            for comment in page
        ]
        return sorted(found, key=lambda comment: (comment.created, comment.id))

    async def _pages(self, path: str, params: Mapping[str, Any]) -> AsyncIterator[list[Any]]:
        """Each page of a list, until the last that Vikunja's pagination header names."""
        page = 1
        while True:
            response = await self._api.request(
                "GET", path, params={**params, "page": page, "per_page": PER_PAGE}
            )
            yield response.json() or []
            if page >= int(response.headers.get("x-pagination-total-pages", 1)):
                return
            page += 1

    async def _label(self, task: _Task, titles: tuple[str, ...]) -> None:
        """Give a task exactly these labels, adding and removing one at a time."""
        held = {label.title: label.id for label in task.labels or ()}
        for title in dict.fromkeys(titles):
            if title not in held:
                label = {"label_id": await self._label_id(title)}
                await self._api.request("PUT", f"/tasks/{task.id}/labels", json=label)
        for title, label_id in held.items():
            if title not in titles:
                await self._api.request("DELETE", f"/tasks/{task.id}/labels/{label_id}")

    async def _label_id(self, title: str) -> int:
        """A label's id by its title, made if there is none."""
        if title not in self._labels:
            response = await self._api.request("GET", "/labels", params={"s": title})
            found = _LABELS.validate_json(response.content or b"null") or []
            same = [label.id for label in found if label.title == title]
            if same:
                self._labels[title] = same[0]
            else:
                made = await self._api.request("PUT", "/labels", json={"title": title})
                self._labels[title] = _Label.model_validate_json(made.content).id
        return self._labels[title]

    def _ref(self, task: _Task) -> ItemRef:
        return ItemRef(
            project=str(task.project_id),
            id=str(task.id),
            number=task.index,
            name=task.identifier,
            key=self._key(task.description),
        )

    def _item(self, task: _Task) -> Item:
        return Item(
            ref=self._ref(task),
            title=task.title,
            description=self._unmarked(task.description),
            state="done" if task.done else "todo",
            priority=_priority(task.priority),
            labels=tuple(sorted(label.title for label in task.labels or ())),
            assignees=tuple(sorted(str(user.id) for user in task.assignees or ())),
            updated_at=task.updated,
        )


def vikunja(client: httpx.AsyncClient) -> Connect:
    """Connect each lattice workspace to its tenant's Vikunja, through one shared client."""

    def connect(credentials: TrackerCredentials, source: str) -> VikunjaTracker:
        return VikunjaTracker(credentials, source, client=client)

    return connect


def _done(state: State | None) -> bool:
    return state in ("done", "cancelled")


def _priority(priority: int) -> Priority:
    named: list[Priority] = [p for p, n in _PRIORITIES.items() if n == priority]
    return named[0] if named else "urgent"


def _order(item: Item) -> tuple[datetime, int]:
    return (item.updated_at, int(item.ref.id))
