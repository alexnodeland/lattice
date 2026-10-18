"""relayr's tracker connector in portalr's test application: acme's ``notes`` files into a tracker.

The tracker is relayr's ``FakeTracker``, in memory, behind the ``tracker:plane`` integration, so
the UIs show it as Plane. A triage run that is dead-lettered is filed, keyed by its run, by the
rule ``portalr:file-dead-letter``; a change a person makes to an item comes back as a
``tracker:item_changed`` event, which ``portalr:follow-up`` reacts to. The scenarios stand in for
that person through ``POST /tracker/edits``, which only this application has.
"""

import html
from collections.abc import Mapping
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from reflexr import F, Rule, on, run
from reflexr.core import RunDeadLettered
from reflexr.workspace import Action, Reaction, Workspaces
from relayr.ledger import InMemoryLedger, WorkspaceKey
from relayr.outbound import Allowlist
from relayr.trackers import (
    Deleted,
    FakeTracker,
    ItemDraft,
    ItemFields,
    TrackerBinding,
    TrackerCredentials,
    TrackerFollowers,
    Trackers,
)
from relayr.trackers.events import ItemChanged

NOTES: Final = WorkspaceKey("acme", "notes")
PROJECT: Final = "ops"
BASE_URL: Final = "https://tracker.portalr.test"
"""Where the fake tracker's items are linked: never opened, only checked."""

FILE_DEAD_LETTER: Final = "portalr:file-dead-letter"
FOLLOW_UP: Final = "portalr:follow-up"

RULES: Final = (
    Rule(
        name=FILE_DEAD_LETTER,
        description="A run was dead-lettered: file it in the tracker.",
        when=on(RunDeadLettered).where(F.rule.ne(FILE_DEAD_LETTER)),
        then=run("file-dead-letter"),
    ),
    Rule(
        name=FOLLOW_UP,
        description="A person changed an item in the tracker: follow it up.",
        when=on(ItemChanged),
        then=run("follow-up"),
    ),
)

CREDENTIALS: Final = TrackerCredentials(
    base_url=BASE_URL, api_key="portalr-test", webhook_secret="portalr-test"
)


class Edit(BaseModel):
    """A person's change to an item, by what people call it: its title."""

    name: str
    title: str


class Tracking:
    """The fake tracker, the connector bound to acme's ``notes``, and its follower."""

    def __init__(self) -> None:
        self.tracker = FakeTracker(api_key=CREDENTIALS.api_key)

        async def credentials(_tenant: str) -> TrackerCredentials:
            return CREDENTIALS

        self.trackers = Trackers(
            InMemoryLedger(),
            connect=self.tracker.connect,
            credentials=credentials,
            bindings={NOTES: TrackerBinding(project=PROJECT, labels=("lattice",))},
            allowlists={FILE_DEAD_LETTER: Allowlist(trackers=True)},
            integration="tracker:plane",
            budget=1000,
        )
        self._followers: TrackerFollowers | None = None

    @property
    def followers(self) -> TrackerFollowers:
        """The follower of each bound workspace, once :meth:`connect` made them."""
        assert self._followers is not None, "the application connects the tracker first"
        return self._followers

    def connect(self, workspaces: Workspaces) -> None:
        """Follow the bound workspace into reflexr's workspaces, reading every 200 ms."""
        self._followers = TrackerFollowers(
            self.trackers, workspaces, interval=timedelta(milliseconds=200)
        )

    async def watch(self, tenant_id: str, workspace_id: str) -> None:
        """reflexr's ``on_open``: follow a bound workspace once it opens."""
        await self.followers.watch(tenant_id, workspace_id)

    def actions(self) -> Mapping[str, Action[None]]:
        """The rules' actions: file a dead-lettered run; follow a change up, by doing nothing."""

        async def file_dead_letter(reaction: Reaction[None]) -> None:
            failed = reaction.events[-1].event
            assert isinstance(failed, RunDeadLettered)
            draft = ItemDraft(
                title=f"{failed.rule} failed",
                description=f"<p>Run <code>{html.escape(failed.run_id)}</code> failed.</p>",
                priority="high",
            )
            item = await self.trackers.acting(reaction).ensure_item(
                draft, key=f"dead-letter/{failed.run_id}"
            )
            assert not isinstance(item, Deleted), "no one deletes the scenarios' items"

        async def follow_up(reaction: Reaction[None]) -> None:
            """Nothing: the run itself, fired by the change, is what the scenarios look for."""

        return {"file-dead-letter": file_dead_letter, "follow-up": follow_up}

    def router(self) -> APIRouter:
        """``POST /tracker/edits``: a person renames an item in the tracker, for the scenarios."""
        router = APIRouter(include_in_schema=False)

        @router.post("/tracker/edits", status_code=204)
        async def edit(change: Edit) -> None:
            # The follower reads the project first, as it would have in the while a person takes:
            # a change to an item it has never read is its first snapshot, and not a change.
            await self.followers.poll(*NOTES)
            for item in self.tracker.items_in(PROJECT):
                if item.ref.name == change.name:
                    self.tracker.edit(item.ref, ItemFields(title=change.title))
                    return
            raise HTTPException(404, f"no item {change.name}")

        return router
