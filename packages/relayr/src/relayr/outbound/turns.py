"""Which rule's run an agent turn acting for the rule continues.

A turn acts for the author of the messages it carries out, one author per turn, and carries out
the oldest messages no turn has taken. So a turn that acts for a rule carries out the rule's
messages since the rule's last turn in the thread, whatever turns for others came between, and
continues the chain of the run that posted the last of them. Notices start no turn, and are
passed over. The follower reads it when the turn starts; the Langfuse turn context, to tag it.
"""

import artifactr
import artifactr.core as a
from relayr.ledger import Cause, Ledger, WorkspaceKey


async def turn_cause(
    ledger: Ledger,
    source: artifactr.Workspace,
    turn: a.AgentActor,
    *,
    before_seq: int | None = None,
    read_back: int = 100,
) -> Cause | None:
    """Return the run behind a turn that acts for a rule, or None if no run's message is in it.

    Args:
        ledger: Where the run behind each message is recorded.
        source: The turn's workspace in artifactr.
        turn: The turn's agent: its thread and run, and the rule's actor it acts for.
        before_seq: Read the thread back from here; from its head by default.
        read_back: How many envelopes to read back at a time.
    """
    rule = turn.on_behalf_of
    key = WorkspaceKey(source.tenant_id, source.workspace_id)
    before = before_seq
    while page := await source.read(before_seq=before, threads={turn.thread_id}, last=read_back):
        for earlier in reversed(page):
            match earlier:
                case a.Envelope(
                    event=a.MessagePosted(kind="message", message_id=message_id), actor=actor
                ) if actor == rule:
                    return await ledger.cause(key, "message", message_id)
                case a.Envelope(
                    event=a.RunStarted(run_id=run_id), actor=a.AgentActor(on_behalf_of=acting)
                ) if acting == rule and run_id != turn.run_id:
                    return None  # an earlier turn for the rule took what came before it
                case _:
                    pass
        before = page[0].seq
    return None
