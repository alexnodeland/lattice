"""FastAPI adapters: the trackers' webhooks, and the tracker connector's reads for the portal.

The webhooks nudge their followers; the reads say what runs filed, and how a follower is doing.

Install `relayr-ai[fastapi]`, and mount the routers beside the libraries':

```python
app.include_router(tracker_router(followers))  # POST /relayr/v1/trackers/{tenant}/{tracker}
app.include_router(  # GET /relayr/v1/workspaces/{workspace_id}/tracker, .../tracker/items
    tracker_reads_router(trackers, automation, resolve_actor=resolve_reflexr_actor)
)
```
"""

from relayr.fastapi.reads import (
    Filed,
    FiledItem,
    Following,
    Reading,
    Writes,
    tracker_reads_router,
)
from relayr.fastapi.router import MAX_BODY, tracker_router

__all__ = [
    "MAX_BODY",
    "Filed",
    "FiledItem",
    "Following",
    "Reading",
    "Writes",
    "tracker_reads_router",
    "tracker_router",
]
