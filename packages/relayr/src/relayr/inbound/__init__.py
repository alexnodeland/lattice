"""The inbound adapter: a follower per workspace, bridging artifactr's events into reflexr.

```python
followers = Followers(collaboration, automation, ledger, projections=projections)
await followers.resume()  # every workspace the ledger knows
...
await followers.aclose()
```

The followers start from the libraries' `on_open` hook, `followers.watch`, which the
application composes with its other ones, such as the feedback mirrors'.
"""

from relayr.inbound.followers import FOLLOWER, SAVE_EVERY, SOURCE, Followers

__all__ = ["FOLLOWER", "SAVE_EVERY", "SOURCE", "Followers"]
