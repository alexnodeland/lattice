"""Which rule's run an agent turn acting for the rule continues.

A turn's `run_started` names the messages it carries out, oldest first (artifactr ADR-0065).
A turn acting for a rule continues the chain of the run that posted the last of them that a run
posted. Notices start no turn, so none is among them. The follower reads it when the turn starts;
the Langfuse turn context, to tag it.
"""

from collections.abc import Sequence

import artifactr.core as a
from relayr.ledger import Cause, Ledger, WorkspaceKey


async def turn_cause(
    ledger: Ledger, workspace: WorkspaceKey, message_ids: Sequence[a.MessageId]
) -> Cause | None:
    """Return the run behind a turn, or None if no run's message is among those it carries out.

    Args:
        ledger: Where the run behind each message is recorded.
        workspace: The turn's workspace.
        message_ids: The messages the turn carries out, oldest first, as its `run_started`
            names them.
    """
    for message_id in reversed(message_ids):
        if (cause := await ledger.cause(workspace, "message", message_id)) is not None:
            return cause
    return None
