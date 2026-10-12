"""The outbound adapter: the runs of rules act in artifactr, each as its rule's own participant.

A function action acts through [`Outbound.acting`][relayr.outbound.Outbound.acting], an agent
through [`ArtifactrCapability`][relayr.outbound.ArtifactrCapability]:

```python
outbound = Outbound(collaboration, ledger, allowlists={"ops:timeline": Allowlist(direct=...)})


async def log_deploy(reaction: Reaction[Deps]) -> None:
    acting = reaction.deps.outbound.acting(reaction)
    await acting.edit(timeline_id, f"/entries/{reaction.run_id}", "deployed")
    await acting.notice("Added to the timeline.")
```

Writes are proposals and notices by default, in the threads of the events that made the rule
fire; a rule's [`Allowlist`][relayr.outbound.Allowlist] grants more.
"""

from relayr.outbound.actions import (
    RULES,
    NotAllowed,
    Outbound,
    Refused,
    RunActions,
    is_rule_actor,
    rule_actor,
)
from relayr.outbound.allowlist import Allowlist
from relayr.outbound.capability import ArtifactrCapability

__all__ = [
    "RULES",
    "Allowlist",
    "ArtifactrCapability",
    "NotAllowed",
    "Outbound",
    "Refused",
    "RunActions",
    "is_rule_actor",
    "rule_actor",
]
