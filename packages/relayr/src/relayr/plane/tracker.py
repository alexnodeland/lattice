"""Plane Community edition's public REST API (v1.4), as the tracker port.

Every item, comment and label lattice writes carries Plane's external ids: `external_id`, its
key, and `external_source`, the lattice workspace. A `POST` with a pair already used answers 409
with the existing id, which `create` and `comment` return as found; `find` asks for the pair,
which reads archived, draft and triage items as well, so an item lattice filed is read that way
and an archived one is never taken for a deleted one. Plane's work items list and its read by id
leave those out.

Plane answers an invalid key with 403 and a missing one with 401; both are `Unauthorized`.
"""

from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

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
    Refused,
    State,
    TrackerCredentials,
)
from relayr.trackers.http import Api
from relayr.trackers.signatures import signed

SIGNATURE: Final = "x-plane-signature"
"""The header Plane signs a webhook in: HMAC-SHA256, hex, over `json.dumps` of its payload, which
is the body it sends."""

INTEGRATION: Final = "tracker:plane"
"""Plane's key among the application's integrations (`relayr.integrations`)."""

PER_PAGE: Final = 1000
"""Plane's largest page."""

_GROUPS: Final[dict[State, str]] = {
    "backlog": "backlog",
    "todo": "unstarted",
    "started": "started",
    "done": "completed",
    "cancelled": "cancelled",
}
"""Plane's state groups by the port's states."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _Issue(_Model):
    id: str
    project: str
    sequence_id: int
    name: str
    description_html: str
    state: str
    priority: Priority
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    updated_at: datetime
    updated_by: str | None
    external_id: str | None
    external_source: str | None


class _Comment(_Model):
    id: str
    comment_html: str
    actor: str | None
    created_at: datetime
    external_id: str | None
    external_source: str | None


class _State(_Model):
    id: str
    group: str
    default: bool
    sequence: float


class _Label(_Model):
    id: str
    name: str


class _Project(_Model):
    identifier: str


class _Found(_Model):
    """Plane's 409: what the external ids already name."""

    id: str


class _Page(_Model):
    results: tuple[dict[str, Any], ...]
    next_cursor: str
    next_page_results: bool


class _Hook(_Model):
    workspace_slug: str
    data: dict[str, Any]


class PlaneTracker:
    """One tenant's Plane workspace, as one lattice workspace writes to it.

    Args:
        credentials: The tenant's: Plane's URL, an API key of the tenant's own Plane user, its
            webhooks' secret, and its workspace's slug.
        source: The lattice workspace, `lattice:<tenant>/<workspace>`: Plane's
            `external_source` on everything it writes.
        client: The HTTP client, which the application shares and closes.
    """

    def __init__(
        self, credentials: TrackerCredentials, source: str, *, client: httpx.AsyncClient
    ) -> None:
        base_url = credentials.base_url.rstrip("/")
        self._api = Api(
            client,
            f"{base_url}/api/v1/workspaces/{credentials.workspace}",
            {"X-Api-Key": credentials.api_key},
        )
        self._web = f"{base_url}/{credentials.workspace}"
        self._workspace = credentials.workspace
        self._secret = credentials.webhook_secret.encode()
        self._source = source
        self._identifiers: dict[ProjectId, str] = {}
        self._states: dict[ProjectId, list[_State]] = {}
        self._labels: dict[ProjectId, dict[str, str]] = {}

    async def find(self, project: ProjectId, key: ItemKey) -> ItemRef | None:
        """Return the item Plane's external ids name, archived or not, or None."""
        issue = await self._external(project, key)
        return None if issue is None else await self._ref(issue)

    async def create(self, project: ProjectId, key: ItemKey, draft: ItemDraft) -> ItemRef:
        """Create a work item with the key as its external id; a used key returns its item."""
        sent: dict[str, Any] = {
            "name": draft.title,
            "description_html": draft.description,
            "priority": draft.priority or "none",
            "labels": [await self._label(project, name) for name in dict.fromkeys(draft.labels)],
            **self._pair(key),
        }
        if draft.state is not None:
            sent["state"] = await self._state(project, draft.state)
        response = await self._api.request(
            "POST", f"/projects/{project}/work-items/", json=sent, answered=(409,)
        )
        if response.status_code == 409:
            response = await self._api.request(
                "GET", f"/projects/{project}/work-items/", params=self._pair(key)
            )
        return await self._ref(_Issue.model_validate_json(response.content))

    async def item(self, ref: ItemRef) -> Item | None:
        """Return a work item's snapshot, or None if it was deleted.

        An item lattice filed is read by its external ids, which find it archived too; any other
        by its id, which doesn't.
        """
        issue = await self._issue(ref)
        return None if issue is None else await self._item(issue)

    async def update(self, ref: ItemRef, fields: ItemFields) -> None:
        """Patch the fields given; labels replace the item's."""
        sent: dict[str, Any] = {}
        if fields.title is not None:
            sent["name"] = fields.title
        if fields.description is not None:
            sent["description_html"] = fields.description
        if fields.priority is not None:
            sent["priority"] = fields.priority
        if fields.state is not None:
            sent["state"] = await self._state(ref.project, fields.state)
        if fields.labels is not None:
            sent["labels"] = [await self._label(ref.project, name) for name in fields.labels]
        try:
            await self._api.request(
                "PATCH", f"/projects/{ref.project}/work-items/{ref.id}/", json=sent
            )
        except Refused:
            # A state or label deleted since they were read: read them again next time.
            self._forget(ref.project)
            raise

    async def comment(self, ref: ItemRef, key: CommentKey, body: str) -> CommentRef:
        """Post a comment with the key as its external id; a used key returns its comment.

        The item is read first: Plane deletes a work item softly, and posts a comment on a
        deleted one with a 201, unseen.
        """
        if await self._issue(ref) is None:
            raise NotFound(f"work item {ref.name} was deleted")
        sent = {"comment_html": body, **self._pair(key)}
        response = await self._api.request(
            "POST",
            f"/projects/{ref.project}/work-items/{ref.id}/comments/",
            json=sent,
            answered=(409,),
        )
        found = _Found.model_validate_json(response.content)
        return CommentRef(item=ref.id, id=found.id)

    async def items(self, project: ProjectId, after: Cursor | None) -> Page[Item]:
        """Return the project's listed work items updated after a cursor, by `updated_at` then id.

        Plane CE filters nothing by time, so every page of the list is read, 1000 at a time, in
        the order items were made, which a change during the read doesn't reshuffle.
        """
        issues = [
            _Issue.model_validate(issue)
            async for issue in self._listed(
                f"/projects/{project}/work-items/", {"order_by": "created_at"}
            )
        ]
        found = sorted([await self._item(issue) for issue in issues], key=_order)
        if after is not None:
            found = [item for item in found if _order(item) > (after.updated_at, after.id)]
        last = found[-1] if found else None
        return Page(
            items=tuple(found),
            next=after if last is None else Cursor(updated_at=last.updated_at, id=last.ref.id),
        )

    async def comments(self, ref: ItemRef, after: CommentRef | None) -> list[Comment]:
        """Return a work item's comments after one, oldest first, or all of them."""
        path = f"/projects/{ref.project}/work-items/{ref.id}/comments/"
        found = sorted(
            [_Comment.model_validate(comment) async for comment in self._listed(path, {})],
            key=lambda comment: (comment.created_at, comment.id),
        )
        comments = [
            Comment(
                ref=CommentRef(item=ref.id, id=comment.id),
                body=comment.comment_html,
                author=comment.actor,
                created_at=comment.created_at,
                key=self._own(comment.external_id, comment.external_source),
            )
            for comment in found
        ]
        if after is None:
            return comments
        ids = [comment.ref.id for comment in comments]
        return comments[ids.index(after.id) + 1 :] if after.id in ids else comments

    def nudge(self, headers: Mapping[str, str], body: bytes) -> Nudge | None:
        """Verify a webhook's signature over its bytes and its workspace, and return its project."""
        if not signed(headers, body, self._secret, SIGNATURE):
            return None
        try:
            hook = _Hook.model_validate_json(body)
        except ValidationError:
            return None
        project = hook.data.get("project")
        if hook.workspace_slug != self._workspace or not isinstance(project, str):
            return None
        return Nudge(project=project)

    def link(self, ref: ItemRef) -> str:
        """Return the work item's page: `<base>/<workspace>/browse/<PROJECT>-<number>/`."""
        return f"{self._web}/browse/{ref.name}/"

    # ─── how ──────────────────────────────────────────────────────────────────

    def _own(self, key: str | None, source: str | None) -> str | None:
        return key if source == self._source else None

    def _pair(self, key: str) -> dict[str, str]:
        """Plane's external ids for a key."""
        return {"external_id": key, "external_source": self._source}

    async def _issue(self, ref: ItemRef) -> _Issue | None:
        """A work item by its external ids if lattice filed it, archived or not; else by its id."""
        if ref.key is not None:
            return await self._external(ref.project, ref.key)
        response = await self._api.request(
            "GET", f"/projects/{ref.project}/work-items/{ref.id}/", answered=(404,)
        )
        found = response.status_code != 404
        return _Issue.model_validate_json(response.content) if found else None

    async def _external(self, project: ProjectId, key: ItemKey) -> _Issue | None:
        response = await self._api.request(
            "GET", f"/projects/{project}/work-items/", params=self._pair(key), answered=(404,)
        )
        found = response.status_code != 404
        return _Issue.model_validate_json(response.content) if found else None

    async def _listed(self, path: str, params: Mapping[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Each result of a list, page by page."""
        cursor = f"{PER_PAGE}:0:0"
        while True:
            response = await self._api.request(
                "GET", path, params={**params, "per_page": PER_PAGE, "cursor": cursor}
            )
            page = _Page.model_validate_json(response.content)
            for result in page.results:
                yield result
            if not page.next_page_results:
                return
            cursor = page.next_cursor

    async def _ref(self, issue: _Issue) -> ItemRef:
        if issue.project not in self._identifiers:
            response = await self._api.request("GET", f"/projects/{issue.project}/")
            self._identifiers[issue.project] = _Project.model_validate_json(
                response.content
            ).identifier
        return ItemRef(
            project=issue.project,
            id=issue.id,
            number=issue.sequence_id,
            name=f"{self._identifiers[issue.project]}-{issue.sequence_id}",
            key=self._own(issue.external_id, issue.external_source),
        )

    def _forget(self, project: ProjectId) -> None:
        """Forget a project's states and labels, to read them again."""
        self._states.pop(project, None)
        self._labels.pop(project, None)

    async def _item(self, issue: _Issue) -> Item:
        states = {state.id: state.group for state in await self._project_states(issue.project)}
        labels = await self._project_labels(issue.project)
        if issue.state not in states or not set(issue.labels) <= set(labels.values()):
            # A state or label made since they were read: read them again.
            self._forget(issue.project)
            states = {s.id: s.group for s in await self._project_states(issue.project)}
            labels = await self._project_labels(issue.project)
        names = {label_id: name for name, label_id in labels.items()}
        return Item(
            ref=await self._ref(issue),
            title=issue.name,
            description=issue.description_html,
            state=_state(states.get(issue.state, "backlog")),
            priority=issue.priority,
            labels=tuple(sorted(names[label] for label in issue.labels if label in names)),
            assignees=tuple(sorted(issue.assignees)),
            updated_at=issue.updated_at,
            updated_by=issue.updated_by,
        )

    async def _project_states(self, project: ProjectId) -> list[_State]:
        if project not in self._states:
            self._states[project] = [
                _State.model_validate(state)
                async for state in self._listed(f"/projects/{project}/states/", {})
            ]
        return self._states[project]

    async def _state(self, project: ProjectId, state: State) -> str:
        """The id of the project's state for a port's state: its group's default, or first."""
        group = [s for s in await self._project_states(project) if s.group == _GROUPS[state]]
        group.sort(key=lambda s: (not s.default, s.sequence))
        if not group:
            raise Refused(f"project {project} has no {_GROUPS[state]} state")
        return group[0].id

    async def _project_labels(self, project: ProjectId) -> dict[str, str]:
        if project not in self._labels:
            self._labels[project] = {
                label.name: label.id
                for label in [
                    _Label.model_validate(label)
                    async for label in self._listed(f"/projects/{project}/labels/", {})
                ]
            }
        return self._labels[project]

    async def _label(self, project: ProjectId, name: str) -> str:
        """A label's id by its name, made with external ids if the project has none."""
        labels = await self._project_labels(project)
        if name not in labels:
            sent = {"name": name, **self._pair(f"label/{name}")}
            response = await self._api.request(
                "POST", f"/projects/{project}/labels/", json=sent, answered=(409,)
            )
            labels[name] = _Found.model_validate_json(response.content).id
        return labels[name]


def plane(client: httpx.AsyncClient) -> Connect:
    """Connect each lattice workspace to its tenant's Plane, through one shared client."""

    def connect(credentials: TrackerCredentials, source: str) -> PlaneTracker:
        return PlaneTracker(credentials, source, client=client)

    return connect


def _state(group: str) -> State:
    """The port's state for a Plane state group; triage reads as backlog."""
    named: list[State] = [state for state, g in _GROUPS.items() if g == group]
    return named[0] if named else "backlog"


def _order(item: Item) -> tuple[datetime, str]:
    return (item.updated_at, item.ref.id)
