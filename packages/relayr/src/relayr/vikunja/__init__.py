"""The Vikunja adapter (lattice RFC-0004): the tracker port over Vikunja's REST API.

Install `relayr-ai[vikunja]`, and connect each workspace through one shared client:

```python
http = httpx.AsyncClient()
trackers = Trackers(
    ledger, connect=vikunja(http), integration=INTEGRATION, credentials=..., bindings=...
)
```
"""

from relayr.vikunja.tracker import INTEGRATION, VikunjaTracker, vikunja

__all__ = ["INTEGRATION", "VikunjaTracker", "vikunja"]
