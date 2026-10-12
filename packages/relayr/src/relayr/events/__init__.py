"""The bridged event types, and the projections that choose what each envelope becomes.

artifactr's events reach reflexr as types in the `artifactr` namespace, such as
`artifactr:message_posted`, under [`ArtifactrEvent`][relayr.events.ArtifactrEvent]. Give
[`BRIDGED`][relayr.events.BRIDGED] to reflexr's `Workspaces(events=...)` with the application's
own types, and register projections for the application's `app_event`s and artifact kinds:

```python
projections = Projections(app_events={"deploy": deployed}, artifacts={"timeline": timeline})
```
"""

from relayr.events.projections import Projection, Projections, bridged
from relayr.events.types import (
    BRIDGED,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    ArtifactrEvent,
    FeedbackGiven,
    MessagePosted,
    ProposalCreated,
    ProposalResolved,
    TurnEnded,
)

__all__ = [
    "BRIDGED",
    "ArtifactArchived",
    "ArtifactChanged",
    "ArtifactCreated",
    "ArtifactrEvent",
    "FeedbackGiven",
    "MessagePosted",
    "Projection",
    "Projections",
    "ProposalCreated",
    "ProposalResolved",
    "TurnEnded",
    "bridged",
]
