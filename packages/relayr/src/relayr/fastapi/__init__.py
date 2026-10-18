"""FastAPI adapters: the route the trackers' webhooks nudge their followers through.

Install `relayr-ai[fastapi]`, and mount the router beside the libraries':

```python
app.include_router(tracker_router(followers))  # POST /relayr/v1/trackers/{tenant}/{tracker}
```
"""

from relayr.fastapi.router import MAX_BODY, tracker_router

__all__ = ["MAX_BODY", "tracker_router"]
