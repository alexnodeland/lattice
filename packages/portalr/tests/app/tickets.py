"""reflexr in portalr's test application: tickets, a rule that triages them, and thumbs on runs.

A ticket published to a workspace starts a run of ``portalr:triage``, which succeeds, unless its
subject starts with ``fail``: then each attempt fails, the run retries once, and is dead-lettered,
for a scenario to retry or skip. Its retries are short, so that happens within a scenario.

A workspace's admin may install stored rules in the ``tickets`` namespace, which run ``triage``
too, and a daily schedule ticks into every workspace, for the Rules area to list. The tracker's
rules and events are ``tracking.py``'s: a dead-lettered run is filed there, and its changes come
back.
"""

from datetime import timedelta

from grantr.core import Agent as AgentSubject
from grantr.core import RulePrincipal, ServicePrincipal, Subject, User
from grantr.grants import Grants
from reflexr import (
    Actor,
    AgentActor,
    EvaluatorActor,
    Event,
    ExternalAgentActor,
    Feedback,
    RetryPolicy,
    Rule,
    SourceActor,
    SystemActor,
    UserActor,
    on,
    run,
)
from reflexr.core import StoredRules
from reflexr.workspace import InMemoryStorage, Reaction, Reactor, Schedule, Workspaces
from relayr.trackers.events import PUBLISHERS, TRACKED
from tests.app.tracking import RULES as TRACKER_RULES
from tests.app.tracking import Tracking


class PortalrEvent(Event, abstract=True, event_namespace="portalr"):
    """The test application's events, in its namespace."""


class TicketOpened(PortalrEvent, name="ticket.opened"):
    """A ticket, as the scenarios publish it."""

    subject: str


class RunThumbs(Feedback, name="thumbs", targets={"run"}):
    """Whether a run helped, and why."""

    up: bool
    comment: str | None = None


TRIAGE = Rule(
    name="portalr:triage",
    description="A ticket was opened: triage it.",
    when=on(TicketOpened),
    then=run("triage"),
    retry=RetryPolicy(max_attempts=2, backoff=timedelta(milliseconds=200)),
)

STORED = StoredRules(actions={"triage": None}, namespaces={"tickets"})
"""What a workspace's stored rules may do: run ``triage``, named in the ``tickets`` namespace."""

CODE_RULES = frozenset({TRIAGE.name, *(rule.name for rule in TRACKER_RULES)})
"""The application's own rules, whose runs act as the application."""

DIGEST = Schedule(name="portalr:digest", cron="0 9 * * *")
"""A tick into every workspace each morning, which no rule here reads."""


async def triage(reaction: Reaction[None]) -> dict[str, str]:
    """Triage the ticket, or fail as its subject says."""
    subject = str(reaction.events[-1].event.model_dump().get("subject", ""))
    if subject.startswith("fail"):
        raise RuntimeError(f"the ticket asked to fail: {subject}")
    return {"triaged": subject}


def subject(application: ServicePrincipal, workspace: str | None, actor: Actor) -> Subject:
    """Who grantr checks for a reflexr actor, as the template's ``reflexr_subject`` maps them: a
    person, and a client acting for one, as them; a client with a key as its principal; the code
    rule's runs, and the application's own system, as the application; a stored rule's runs as
    the rule; any other agent as no one. The tracker's follower publishes as a source, so as the
    application."""
    match actor:
        case UserActor():
            return User(id=actor.id)
        case ExternalAgentActor(on_behalf_of=None):
            return ServicePrincipal(id=actor.client_id)
        case ExternalAgentActor(on_behalf_of=UserActor(id=person)):
            return User(id=person)
        case AgentActor(rule=rule) if rule in CODE_RULES:
            return application
        case AgentActor(rule=rule) if workspace is not None:
            return RulePrincipal(workspace=workspace, rule=rule)
        case SystemActor() | EvaluatorActor() | SourceActor():
            return application
        case _:  # an agent of no rule this application has holds nothing
            return AgentSubject()


def automation(
    grants: Grants, application: ServicePrincipal, tracking: Tracking
) -> tuple[Workspaces, Reactor[None]]:
    """reflexr's workspaces, checked by grantr, the reactor that runs their rules, and the
    tracker's follower connected to them."""

    def checked_as(_tenant: str, workspace: str | None, actor: Actor) -> Subject:
        return subject(application, workspace, actor)

    hooks = grants.hooks(checked_as)
    workspaces = Workspaces(
        InMemoryStorage(),
        events=[TicketOpened, *TRACKED],
        rules=[TRIAGE, *TRACKER_RULES],
        stored_rules=STORED,
        schedules=[DIGEST],
        authorize=hooks.authorize,
        publishers=PUBLISHERS,
        on_open=tracking.watch,
    )
    tracking.connect(workspaces)
    actions = {"triage": triage, **tracking.actions()}
    return workspaces, Reactor[None](workspaces, actions=actions)
