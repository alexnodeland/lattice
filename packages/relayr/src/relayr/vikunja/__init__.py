"""The Vikunja adapter (lattice RFC-0004): the tracker port over Vikunja's REST API.

Install `relayr-ai[vikunja]`, and connect each workspace through one shared client:

```python
http = httpx.AsyncClient()
trackers = Trackers(ledger, connect=vikunja(http), credentials=..., bindings=...)
```
"""

from relayr.vikunja.tracker import VikunjaTracker, vikunja

__all__ = ["VikunjaTracker", "vikunja"]
