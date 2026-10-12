# Evaluating the bridge's rules

relayr scores how people receive what rules propose, and measures rules from chat through their life ([ADR-0031](../adr/0031-proposal-outcomes-and-the-measures.md)). Install the `evals` extra for `relayr.evals`: `relayr-ai[evals]`.

## Proposal outcomes

```python
from relayr.evals import RULES as EVALUATION_RULES, Outcomes

automation = reflexr.workspace.Workspaces(storage, rules=[*APP_RULES, *EVALUATION_RULES])
reactor = Reactor(automation, actions={..., **Outcomes(collaboration, ledger).actions})
```

`relayr:proposal-outcome` gives the run behind each resolved proposal a `ProposalOutcome`, as relayr's evaluator:

| Outcome | When |
|---|---|
| `accepted` | The person accepted it as proposed, or with changes that change nothing |
| `edited` | The person accepted it with changes of their own |
| `rejected` | The person rejected it |

reflexr's feedback mirror carries each outcome on to a Langfuse score on the run. A retried or replayed resolution is scored once.

## Measures

- **`proposal_rates(workspace)`** counts the outcomes by the rule whose run proposed. Each `ProposalRates` gives `acceptance`, the share accepted with or without edits, and `edit_rate`, the share of those that people edited.
- **`rule_conversion(source, workspace, now=...)`** follows rules drafted in chat:
  - how many were proposed, accepted and put live;
  - of those live for at least `survival`, how many were never archived since.
- **`history(source, artifact_id)`** gives an artifact's versions to evalr's measures, such as `measure_rewrites`, which counts the agent's versions that people rewrote.

reflexr's `time_to_resolution` measures a causal chain from its first event to the event that resolves it.

## Cost per chain

A turn a rule's run started is tagged `chain:<correlation id>` in Langfuse ([ADR-0024](../adr/0024-langfuse-sessions-tagged-with-each-other.md)). Filter Langfuse's traces by that tag to see what a chain cost, the turns it started included. LiteLLM's spend for the chain is in the same traces.
