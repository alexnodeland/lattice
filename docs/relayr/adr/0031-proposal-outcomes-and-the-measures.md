# ADR-0031: Proposal outcomes, and the measures

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds relayr's part of phase 6 of [RFC-0001](../rfcs/0001-v0.1-implementation-plan.md), as [stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md#evaluation) designs it.

## Context

RFC-0002 measures the bridge's rules in four ways:

- by how people resolve their proposals, as feedback on the runs that proposed;
- by acceptance and edit rates per rule;
- by how many rules drafted in chat go live, and stay live;
- by the measures the libraries and evalr already have, such as `measure_rewrites` over an artifact's history and `time_to_resolution` over a chain.

## Decision

- **An online rule scores each run's proposals.** `relayr:proposal-outcome` fires on `artifactr:proposal_resolved` where the proposer is an external agent. Its action, `Outcomes.score`:
  - re-reads the proposal in artifactr, rather than trust the bridged event;
  - scores only a proposal a rule's participant made that the ledger traces to a run;
  - gives that run a `ProposalOutcome`, as relayr's evaluator, `EvaluatorActor(name="relayr:proposal-outcome")`, which reflexr's feedback mirror carries on to a Langfuse score on the run.
- **The outcome says whether the person changed the proposal.**
  - `accepted`: the artifact the acceptance made is what the proposal alone would have made.
  - `edited`: it differs, because the person's changes did something.
  - `rejected`: the proposal was rejected.
  - A `changes` field that changes nothing is `accepted`. An archive takes no changes, so it is `accepted` or `rejected`.
- **Each resolution is scored once.** Before scoring, the action looks for the evaluator's feedback on the run, given by a run that matched the same resolution. So a retried attempt, and a rule replayed with `refire`, score nothing twice.
- **The measures are functions over the logs:**
  - `proposal_rates`: the outcomes, counted by the rule whose run proposed, with their acceptance and edit rates.
  - `rule_conversion`: rule drafts proposed, accepted, put live by relayr, and still live after `survival` (30 days by default). Installs are counted from relayr's own `rule_installed` facts. A rule archived since, in reflexr directly, through its artifact or by anyone, does not survive.
  - `history`: an artifact's versions as evalr's `History`, for `measure_rewrites`. A person's version is the person's; an agent's, a rule's or a client's is the agent's. Archives change no text, so they are left out.
- **evalr is a new extra, `relayr-ai[evals]`.** `relayr.evals` builds evalr's `History`; nothing else in relayr needs evalr.

## Options considered

| Option | For | Against |
|---|---|---|
| **An online rule (chosen)** | Langfuse gets a score on each run as people resolve its proposals | One more code rule for the application to run |
| An offline measure over the logs only | Nothing runs in the application | No score where people look at runs |
| **Edited when the result differs (chosen)** | Means what people did | A diff against the proposal's own change |
| Edited when `changes` is present | One field to read | A no-op change would count as an edit |

## Consequences

- Easier: each rule's runs carry how people received what they proposed, and the template's experiment can report acceptance, rewrites and time to resolution.
- Harder: scoring reads the evaluator's earlier feedback once per resolution, to score nothing twice.
- Deferred:
  - bridge lag, as a histogram, is a later telemetry follow-up;
  - cost per chain is a Langfuse query on the `chain:` tag, in the guide;
  - measuring a thread together with the chains it started stays unresolved, as RFC-0002 leaves it.
