# ADR-0030: The incident experiment, and its postmortem

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the template's part of phase 6 of [relayr RFC-0001](../../relayr/rfcs/0001-v0.1-implementation-plan.md), on relayr's proposal outcomes and measures ([relayr ADR-0031](../../relayr/adr/0031-proposal-outcomes-and-the-measures.md)).

## Context

Phase 6's exit is that the example's experiment reports acceptance, rewrite rate and time to resolution. The incident example's rules wrote the timeline directly, so no rule proposed anything to accept, and nothing marked an incident's end.

## Decision

- **An incident ends with `incident.resolved`.** `IncidentResolved(service, summary)` fires `close-incident`. Its run finds the service's latest open incident, marks its timeline resolved (`resolved_at`), posts a closing notice in the incident's thread, and proposes a `postmortem` there. A repeated resolution finds the incident resolved, and does nothing.
  - The postmortem is a typed artifact, proposed for review: a summary, the timeline's entries, and follow-ups people add.
  - Its rationale says what it was drawn from: the timeline, with its number of entries, and the resolution.
- **`close-incident` reaches any thread, and trusts only `open-incident`'s record of it.**
  - A resolution from monitoring brings no thread, so the rule's allowlist grants any thread (`threads="any"`) and direct writes to timelines, for `resolved_at`. Its other writes are a proposal and a notice.
  - It acts as the application, a code rule (`CODE_RULES`), which may write in a restricted thread.
  - A timeline's writes are direct, so anyone who may write one could point it at a thread they choose. The rule therefore considers only timelines whose first version `open-incident` wrote, and takes the incident's service and thread from that first version. A timeline anyone else made, or edited since, can't steer it into another thread, restricted or not.
- **relayr's evaluation joins the application.** `relayr:proposal-outcome` is among Automation's rules and the code rules, and the bridge registers its action, with or without `evals`: scoring runs in the application. The template asks for `relayr-ai[evals]`. Each postmortem people accept, edit or reject scores the `close-incident` run that proposed it.
- **The experiment runs through the application itself.** `incident-scenarios` builds the application with `create_app`, in process, on a scripted model and a SQLite file of its own. It plays each example over its REST API, as monitoring and people would: an alert opens the incident, people write in the thread, the incident is resolved, and people accept the postmortem, edit it, or reject it, and in one scenario rewrite it afterwards. `make evals` installs the `evals` dependency group, which brings the HTTP client and SQLite driver this needs.
- **It exercises the measures end to end, and judges nothing.** Each scenario's decisions are scripted, and no model is on the path, so the outcomes are the scripts' own. What it checks is that relayr's measures read what the application wrote. Each example's verdict, an `IncidentReview`, reports:
  - the postmortem's outcome, from `proposal_rates`;
  - how much of the postmortem the rule wrote people rewrote, from evalr's `measure_rewrites` over `relayr.evals.history`, or none without a postmortem;
  - the seconds between the alert and its resolution, from their events' own timestamps.
- **Time to resolution is the alert to its resolution, by service.** reflexr's `time_to_resolution` measures a causal chain, and a resolution that monitoring publishes starts a chain of its own, so it can't tell when an incident ended. Each resolution is paired with the service's latest alert before it.

## Options considered

| Option | For | Against |
|---|---|---|
| **A postmortem proposed on resolution (chosen)** | A rule's proposal people review, so acceptance and edits are real; a useful artifact | One more rule and artifact type in the example |
| Proposed timeline entries | No new rule | A less useful timeline, with direct and proposed writes in one rule |
| Acceptance from rule drafts (`rule_conversion`) | Nothing new | Measures drafts, not a rule's proposals |
| **The application, over REST (chosen)** | The real wiring, as deployed | Slower than the parts alone |
| The parts, wired anew in the experiment | Faster | A second copy of the wiring, which drifts |

## Consequences

- Easier: `make evals` checks the example's incidents end to end, through the same code that serves them, and is where a real evaluation of the rules, with a model on the path, would start.
- Harder: the experiment builds the whole application for each example, so it takes seconds, not milliseconds.
