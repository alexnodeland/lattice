"""Langfuse across the bridge: the tags and user that join a causal chain and a thread.

Install `relayr-ai[langfuse]`, and give the contexts to the libraries in place of their own:

```python
reactor = Reactor(automation, actions=actions, run_context=bridged_run)
runner = Runner(agent, app=app, turn_context=bridged_turns(ledger))
```
"""

from relayr.langfuse.tracing import bridged_run, bridged_turns

__all__ = ["bridged_run", "bridged_turns"]
