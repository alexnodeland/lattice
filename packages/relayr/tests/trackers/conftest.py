"""A workspace bound to a fake tracker, and the reactions of runs that write to it."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

import reflexr
import reflexr.core
import reflexr.workspace as r
from lattice_core.integrations import Integrations
from relayr.integrations import ALWAYS
from relayr.ledger import Ledger, WorkspaceKey
from relayr.outbound import Allowlist
from relayr.trackers import FakeTracker, TrackerBinding, TrackerCredentials, Trackers
from tests.app_types import Deployed
from tests.clock import FakeClock

TENANT = "acme"
KEY = WorkspaceKey(TENANT, "ops")
PROJECT = "ops"
RULE = "ops:file"
SOURCE = "lattice:acme/ops"
CREDENTIALS = TrackerCredentials(
    base_url="https://tracker.test", api_key="key", webhook_secret="secret"
)
BINDING = TrackerBinding(project=PROJECT, labels=("lattice",), priority="medium")
ALLOWED = {RULE: Allowlist(trackers=True)}


@dataclass
class Tenant:
    """The tenant's credentials, as the deployment keeps them, and how often they were asked."""

    credentials: TrackerCredentials = CREDENTIALS
    asked: list[str] = field(default_factory=list[str])

    async def __call__(self, tenant: str) -> TrackerCredentials:
        self.asked.append(tenant)
        return self.credentials


@dataclass
class Switch:
    """lattice-core's integrations port, on or off everywhere, and what it was asked."""

    on: bool = True
    asked: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])

    async def is_enabled(self, tenant_id: str, workspace_id: str | None, key: str, /) -> bool:
        assert workspace_id is not None, "relayr asks in a workspace"
        self.asked.append((tenant_id, workspace_id, key))
        return self.on


@dataclass
class Runs:
    """Runs of the rule in the bound workspace, and the connector they write through."""

    workspaces: r.Workspaces
    workspace: r.Workspace
    trackers: Trackers
    reactions: int = 0

    async def reaction(self, run: reflexr.core.Run | None = None) -> r.Reaction[None]:
        """A reaction to a new run of the rule, or an attempt of a run seen before."""
        if run is None:
            self.reactions += 1
            await self.workspace.publish(Deployed(service=f"svc-{self.reactions}"))
            await r.Reactor(self.workspaces, actions={"file": _idle}, deps=None).evaluate()
            run = max(await self.workspace.runs(), key=lambda run: run.fired_seq)
        return r.Reaction(workspace=self.workspace, run=run, rule=FILE, events=(), deps=None)


FILE = reflexr.Rule(name=RULE, when=reflexr.on(Deployed), then=reflexr.run("file"))


async def _idle(reaction: r.Reaction[None]) -> None:
    """The rule's action, which these tests never run: they act through its reactions."""


@pytest.fixture
def tracker(clock: FakeClock) -> FakeTracker:
    return FakeTracker(clock=clock)


@pytest.fixture
def tenant() -> Tenant:
    return Tenant()


def connector(
    ledger: Ledger,
    tracker: FakeTracker,
    tenant: Tenant,
    clock: FakeClock,
    *,
    allowlists: Mapping[str, Allowlist] = ALLOWED,
    bindings: Mapping[WorkspaceKey, TrackerBinding] | None = None,
    integrations: Integrations = ALWAYS,
) -> Trackers:
    return Trackers(
        ledger,
        connect=tracker.connect,
        credentials=tenant,
        bindings={KEY: BINDING} if bindings is None else bindings,
        allowlists=allowlists,
        integration="tracker:fake",
        integrations=integrations,
        clock=clock,
    )


@pytest.fixture
async def runs(ledger: Ledger, tracker: FakeTracker, tenant: Tenant, clock: FakeClock) -> Runs:
    workspaces = r.Workspaces(
        r.InMemoryStorage(clock=clock), events=(Deployed,), rules=[FILE], clock=clock
    )
    workspace = await workspaces.open(*KEY, actor=reflexr.SourceActor(name="ci"))
    return Runs(workspaces, workspace, connector(ledger, tracker, tenant, clock))


def attempt(reaction: r.Reaction[Any]) -> reflexr.core.Run:
    """The reaction's run, as its next attempt sees it."""
    return reaction.run.model_copy(update={"attempts": reaction.run.attempts + 1})
