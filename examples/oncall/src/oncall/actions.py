"""The actions the rules run: an agent, a graph and functions, all over one ``Reaction``."""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model

from oncall.events import AlertFired
from oncall.rules import SILENCE
from oncall.runbook import runbook_action
from oncall.services import OncallDeps
from oncall.triage import triage_action
from reflexr.workspace import Action, Reaction, with_params


async def page(reaction: Reaction[OncallDeps]) -> dict[str, str]:
    """Page the person on call about a silent service, and raise an alert about it.

    The alert counts towards the service's triage like any other. Its id is derived from the
    run, and the page is deduplicated by the run's id, so a retried run does neither twice.
    """
    service = str(reaction.scope["service"])
    reason = f"no heartbeat from {service} for {SILENCE.total_seconds() / 60:g} minutes"
    await reaction.deps.pager.page(service, reason, key=reaction.run_id)
    await reaction.emit(AlertFired(service=service, severity=8, message=reason))
    return {"paged": service}


class NotifyParams(BaseModel):
    """What a rule that runs ``notify`` says: whose person on call to tell."""

    service: str


async def notify(reaction: Reaction[OncallDeps], params: NotifyParams) -> dict[str, str]:
    """Page a service's person on call with the rule's description, deduplicated by the run's id.

    It is the action rules installed at runtime may run (:data:`oncall.app.STORED_RULES`). They
    have no scope, so the rule names the service in its params.
    """
    reason = reaction.rule.description or reaction.rule.name
    await reaction.deps.pager.page(params.service, reason, key=reaction.run_id)
    return {"paged": params.service}


def build_actions(
    model: Model | str | None = None,
    *,
    capabilities: Sequence[AbstractCapability[Any]] = (),
) -> dict[str, Action[OncallDeps]]:
    """Every action, by the name rules refer to it by.

    Args:
        model: The triage agent's model; see :func:`oncall.triage.build_triage_agent`.
        capabilities: More capabilities for the triage agent, such as its instrumentation.
    """
    triage = triage_action(model, capabilities=capabilities)
    return {
        "triage": triage,
        "runbook": runbook_action(),
        "page": page,
        "notify": with_params(notify, NotifyParams),
    }
