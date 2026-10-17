"""The Plane adapter (lattice RFC-0004): the tracker port over Plane Community edition's API.

Install `relayr-ai[plane]`, and connect each workspace through one shared client:

```python
http = httpx.AsyncClient()
trackers = Trackers(ledger, connect=plane(http), credentials=..., bindings=...)
```
"""

from relayr.plane.tracker import PlaneTracker, plane

__all__ = ["PlaneTracker", "plane"]
