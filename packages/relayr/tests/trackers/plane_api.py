"""Plane Community edition's public API, as its v1.4.2 source reads, for the contract test.

No Plane runs on a pull request (it is 13 services and 4 to 8 GB), and none was run to record
one, so this answers as `apps/api/plane/` at v1.4.2 does, path by path; the responses carry the
serializers' fields. What it follows, and where:

- Routes under `api/v1/workspaces/<slug>/`, `work-items` and their trailing slashes
  (`api/urls/work_item.py`, `label.py`, `state.py`, `project.py`); `X-Api-Key`, a missing one 401
  and an invalid one 403 (`api/middleware/api_authentication.py`, `authentication/adapter`).
- A create whose `external_id` and `external_source` are used answers 409 with the existing
  `id`, among items, archived ones included and deleted ones not (`api/views/issue.py`); so do
  comments and labels, and a label's used name.
- `GET ?external_id=&external_source=` returns one item, archived or not, or 404; the read by id
  and the list leave archived items out (`issue_objects`).
- `updated_by` is null on create and the key's user on a `PATCH`, whose `labels` replace the
  item's (`db/models/base.py`, `api/serializers/issue.py`).
- Lists are pages of `results`, by `cursor` `<per_page>:<page>:0`, 1000 at most
  (`utils/paginator.py`); comments and labels newest first, whatever `order_by` says.
- A webhook's signature is HMAC-SHA256, hex, over `json.dumps(payload)`, which `requests`
  sends as the body (`bgtasks/webhook_task.py`).
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from relayr.trackers import ItemRef

API_KEY = "key"
SLUG = "acme"
USER = "00000000-0000-4000-8000-0000000000aa"
"""The key's user, relayr's Plane user."""

PERSON = "00000000-0000-4000-8000-0000000000bb"
GROUPS = (
    ("Backlog", "backlog", 15000.0),
    ("Todo", "unstarted", 25000.0),
    ("In Progress", "started", 35000.0),
    ("Done", "completed", 45000.0),
    ("Cancelled", "cancelled", 55000.0),
)
"""A project's default states (`db/models/state.py`)."""

NOT_FOUND = {"error": "The requested resource does not exist."}


def _id() -> str:
    return str(uuid.uuid4())


def _page(results: list[dict[str, Any]], cursor: str) -> dict[str, Any]:
    size, page, _ = (int(part) for part in cursor.split(":"))
    chunk = results[page * size : (page + 1) * size]
    more = len(results) > (page + 1) * size
    return {
        "grouped_by": None,
        "sub_grouped_by": None,
        "total_count": len(results),
        "next_cursor": f"{size}:{page + 1}:0",
        "prev_cursor": f"{size}:{page - 1}:1",
        "next_page_results": more,
        "prev_page_results": page > 0,
        "count": len(chunk),
        "total_pages": -(-len(results) // size),
        "total_results": len(results),
        "extra_stats": None,
        "results": chunk,
    }


class PlaneApi:
    """One Plane workspace, `acme`, with one project, `OPS`, answering as Plane's API does."""

    URL = "https://plane.test"

    def __init__(self, *, secret: str, per_page: int = 1000) -> None:
        self.secret = secret
        self.per_page = per_page
        self.project = _id()
        self.workspace = _id()
        self.now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        self.issues: dict[str, dict[str, Any]] = {}
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.labels: list[dict[str, Any]] = []
        self.states = [
            self._row(name=name, group=group, sequence=sequence, default=group == "backlog")
            for name, group, sequence in GROUPS
        ]

    # ─── what a person does ───────────────────────────────────────────────────

    def add(self, title: str) -> ItemRef:
        """File a work item in the web app, with no external ids, as a person does."""
        issue = self._create({"name": title}, by=PERSON).json()
        return ItemRef(
            project=self.project,
            id=issue["id"],
            number=issue["sequence_id"],
            name=f"OPS-{issue['sequence_id']}",
        )

    def reply(self, ref: ItemRef, body: str) -> None:
        """Comment in the web app, as a person does."""
        self._comment(ref.id, {"comment_html": body}, by=PERSON)

    def delete(self, ref: ItemRef) -> None:
        """Delete a work item, which frees its external ids."""
        del self.issues[ref.id]

    def archive(self, ref: ItemRef) -> None:
        """Archive a work item."""
        self.issues[ref.id]["archived_at"] = self.now.date().isoformat()

    def delivery(self) -> tuple[dict[str, str], bytes]:
        """A webhook for a work item's change, signed as Plane signs it."""
        payload = {
            "event": "issue",
            "action": "updated",
            "webhook_id": _id(),
            "workspace_id": self.workspace,
            "workspace_slug": SLUG,
            "data": {"id": _id(), "project": self.project, "name": "Fix login"},
            "activity": {"field": "state", "new_value": _id(), "old_value": _id()},
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Autopilot",
            "X-Plane-Delivery": _id(),
            "X-Plane-Event": "issue",
            "X-Plane-Signature": signature,
        }
        return headers, body

    # ─── what the API answers ─────────────────────────────────────────────────

    def handle(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("x-api-key")
        if key is None:
            return httpx.Response(
                401, json={"detail": "Authentication credentials were not provided."}
            )
        if key != API_KEY:
            return httpx.Response(403, json={"detail": "Given API token is not valid"})
        prefix = f"/api/v1/workspaces/{SLUG}/projects/{self.project}/"
        path = request.url.path
        if not path.startswith(prefix):
            return httpx.Response(
                403, json={"detail": "You do not have permission to perform this action."}
            )
        parts = path.removeprefix(prefix).rstrip("/").split("/") if path != prefix else []
        body = json.loads(request.content) if request.content else {}
        params = request.url.params
        match request.method, parts:
            case "GET", []:
                return httpx.Response(200, json={"id": self.project, "identifier": "OPS"})
            case "GET", ["states"]:
                return self._list(self.states, params)
            case "GET", ["labels"]:
                return self._list(self.labels[::-1], params)
            case "POST", ["labels"]:
                return self._label(body)
            case "GET", ["work-items"] if "external_id" in params:
                found = self._external(self.issues.values(), params)
                return (
                    httpx.Response(200, json=found)
                    if found
                    else httpx.Response(404, json=NOT_FOUND)
                )
            case "GET", ["work-items"]:
                listed = [i for i in self.issues.values() if i["archived_at"] is None]
                listed.sort(key=lambda issue: issue["updated_at"])
                return self._list(listed, params)
            case "POST", ["work-items"]:
                return self._create(body)
            case "GET", ["work-items", issue_id]:
                found = self.issues.get(issue_id)
                if found is None or found["archived_at"] is not None:
                    return httpx.Response(404, json=NOT_FOUND)
                return httpx.Response(200, json=found)
            case "PATCH", ["work-items", issue_id] if issue_id in self.issues:
                return self._patch(self.issues[issue_id], body)
            case "GET", ["work-items", issue_id, "comments"] if issue_id in self.issues:
                return self._list(self.comments[issue_id][::-1], params)
            case "POST", ["work-items", issue_id, "comments"] if issue_id in self.issues:
                return self._comment(issue_id, body)
            case _:
                return httpx.Response(404, json=NOT_FOUND)

    def _tick(self) -> str:
        self.now += timedelta(seconds=1)
        return self.now.isoformat().replace("+00:00", "Z")

    def _row(self, by: str = USER, **fields: Any) -> dict[str, Any]:
        at = self._tick()
        return {
            "id": _id(),
            "created_at": at,
            "updated_at": at,
            "deleted_at": None,
            "created_by": by,
            "updated_by": None,
            "project": self.project,
            "workspace": self.workspace,
            "external_source": None,
            "external_id": None,
            **fields,
        }

    def _list(self, rows: list[dict[str, Any]], params: httpx.QueryParams) -> httpx.Response:
        per_page = int(params.get("per_page", self.per_page))
        if per_page > 1000:
            return httpx.Response(
                400, json={"detail": "Invalid per_page value. Cannot exceed 1000."}
            )
        cursor = params.get("cursor", f"{per_page}:0:0")
        return httpx.Response(200, json=_page(rows, cursor))

    @staticmethod
    def _external(rows: Any, params: Any) -> dict[str, Any] | None:
        pair = (params.get("external_id"), params.get("external_source"))
        return next((r for r in rows if (r["external_id"], r["external_source"]) == pair), None)

    def _conflict(self, rows: Any, body: dict[str, Any], what: str) -> httpx.Response | None:
        if body.get("external_id") and body.get("external_source"):
            found = self._external(rows, body)
            if found is not None:
                error = f"{what} with the same external id and external source already exists"
                return httpx.Response(409, json={"error": error, "id": found["id"]})
        return None

    def _create(self, body: dict[str, Any], by: str = USER) -> httpx.Response:
        if not body.get("name"):
            return httpx.Response(400, json={"name": ["This field is required."]})
        conflict = self._conflict(self.issues.values(), body, "Issue")
        if conflict is not None:
            return conflict
        default = next(s["id"] for s in self.states if s["default"])
        issue = self._row(
            by,
            type_id=None,
            point=None,
            name=body["name"],
            description_html=body.get("description_html") or "<p></p>",
            description_binary=None,
            priority=body.get("priority", "none"),
            start_date=None,
            target_date=None,
            sequence_id=len(self.issues) + 1,
            sort_order=65535.0,
            completed_at=None,
            archived_at=None,
            is_draft=False,
            parent=None,
            state=body.get("state", default),
            estimate_point=None,
            type=None,
            assignees=body.get("assignees", []),
            labels=body.get("labels", []),
        )
        issue["external_id"], issue["external_source"] = (
            body.get("external_id"),
            body.get("external_source"),
        )
        self.issues[issue["id"]] = issue
        self.comments[issue["id"]] = []
        return httpx.Response(201, json=issue)

    def _patch(self, issue: dict[str, Any], body: dict[str, Any]) -> httpx.Response:
        issue.update({k: v for k, v in body.items() if k in issue})
        issue["updated_at"], issue["updated_by"] = self._tick(), USER
        return httpx.Response(200, json=issue)

    def _comment(self, issue_id: str, body: dict[str, Any], by: str = USER) -> httpx.Response:
        every = [c for comments in self.comments.values() for c in comments]
        conflict = self._conflict(every, body, "Work item comment")
        if conflict is not None:
            return conflict
        comment = self._row(
            by,
            comment_html=body["comment_html"],
            attachments=[],
            access="INTERNAL",
            edited_at=None,
            issue=issue_id,
            actor=by,
            parent=None,
            description=_id(),
        )
        comment["external_id"], comment["external_source"] = (
            body.get("external_id"),
            body.get("external_source"),
        )
        # Whether a comment moves its work item's `updated_at` is unverified, so it doesn't here.
        self.comments[issue_id].append(comment)
        return httpx.Response(201, json=comment)

    def _label(self, body: dict[str, Any]) -> httpx.Response:
        conflict = self._conflict(self.labels, body, "Label")
        if conflict is not None:
            return conflict
        same = next((label for label in self.labels if label["name"] == body["name"]), None)
        if same is not None:
            error = "Label with the same name already exists in the project"
            return httpx.Response(409, json={"error": error, "id": same["id"]})
        label = self._row(
            name=body["name"], description="", color="", sort_order=65535.0, parent=None
        )
        label["external_id"], label["external_source"] = (
            body.get("external_id"),
            body.get("external_source"),
        )
        self.labels.append(label)
        return httpx.Response(201, json=label)
