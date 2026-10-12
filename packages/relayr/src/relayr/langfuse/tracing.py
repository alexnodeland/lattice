"""Langfuse attributes across the bridge: the tags and user that join a chain and a thread.

Sessions stay apart (ADR-0004): a thread is artifactr's session, a causal chain reflexr's. These
contexts wrap the libraries' own, `artifactr.langfuse.langfuse_turn`'s attributes and
`reflexr.langfuse.langfuse_run`'s, and add what joins the two:

- a run whose rule fired on bridged events is tagged `thread:<id>` for each of their threads, and
  its user is the person who acted in artifactr, not relayr's source
- a turn acting for a rule, which a rule's message started, is tagged `rule:<name>` and
  `chain:<correlation id>`, the chain of the run that sent the message
"""

import contextlib
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any

from langfuse import propagate_attributes

import artifactr.core as a
from artifactr.agent import Session, TurnContext
from artifactr.langfuse import turn_attributes
from reflexr.langfuse import run_attributes
from reflexr.workspace import Reaction
from relayr.events import ArtifactrEvent
from relayr.ledger import Ledger, WorkspaceKey
from relayr.outbound import RULES, is_rule_actor, turn_cause

MAX_ATTRIBUTE = 200
"""The longest trace attribute value Langfuse accepts."""


@contextlib.asynccontextmanager
async def bridged_run(reaction: Reaction[Any]) -> AsyncGenerator[None]:
    """Propagate a run's Langfuse attributes, with its threads and its person; a `RunContext`.

    Give it to reflexr's `Reactor(run_context=...)` in place of `langfuse_run`.
    """
    attributes = run_attributes(reaction)
    bridged = [e.event for e in reaction.events if isinstance(e.event, ArtifactrEvent)]
    threads = dict.fromkeys(event.thread_id for event in bridged if event.thread_id)
    attributes["tags"] = [*attributes["tags"], *(_limit(f"thread:{t}") for t in threads)]
    if bridged and isinstance(person := bridged[-1].author, a.UserActor):
        attributes["user_id"] = _limit(person.id)
    with propagate_attributes(**attributes):
        yield


def bridged_turns(ledger: Ledger) -> TurnContext:
    """Return a `TurnContext` that propagates a turn's attributes, with its rule and chain.

    Give it to artifactr's `Runner(turn_context=...)` in place of `langfuse_turn`.

    Args:
        ledger: The ledger relayr's adapters share, which holds the run behind each message.
    """

    def turn(session: Session[Any]) -> AbstractAsyncContextManager[object]:
        return _turn(ledger, session)

    return turn


@contextlib.asynccontextmanager
async def _turn(ledger: Ledger, session: Session[Any]) -> AsyncGenerator[None]:
    attributes = await turn_attributes(session)
    match session.workspace.actor:
        case a.AgentActor(on_behalf_of=a.ExternalAgentActor(client_id=client) as rule) if (
            is_rule_actor(rule)
        ):
            tags = [_limit(f"rule:{client.removeprefix(RULES)}")]
            workspace = WorkspaceKey(session.workspace.tenant_id, session.workspace.workspace_id)
            cause = await turn_cause(ledger, workspace, session.message_ids)
            if cause is not None:
                tags.append(_limit(f"chain:{cause.correlation_id}"))
            attributes["tags"] = [*attributes["tags"], *tags]
        case _:
            pass
    with propagate_attributes(**attributes):
        yield


def _limit(value: str) -> str:
    """Make a value acceptable to Langfuse: ASCII, and at most 200 characters."""
    return value.encode("ascii", "replace").decode("ascii")[:MAX_ATTRIBUTE]
