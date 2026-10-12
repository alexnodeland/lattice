# ADR-0030: The incident experiment, and its postmortem

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the template's part of phase 6 of [relayr RFC-0001](../../relayr/rfcs/0001-v0.1-implementation-plan.md), on relayr's proposal outcomes and measures ([relayr ADR-0031](../../relayr/adr/0031-proposal-outcomes-and-the-measures.md)).

## Context

Phase 6's exit is that the example's experiment reports acceptance, rewrite rate and time to resolution. The incident example's rules wrote the timeline directly, so no rule proposed anything to accept, and nothing marked an incident's end.

## Decision

- **An incident ends with `incident.resolved`.** `IncidentResolved(service, summary)` fires `close-incident`, whose run finds the service's latest incident timeline. It posts a closing notice in the incident's thread, and proposes a `postmortem` there.
  - The postmortem is a typed artifact, proposed for review: a summary, the timeline's entries, and follow-ups people add.
  - Its rationale says what it was drawn from: the timeline, with its number of entries, and the resolution.
  - `close-incident` may act in any thread (`threads="any"`), since a resolution from monitoring brings no thread with it. Its writes are still a proposal and a notice.
- **relayr's evaluation joins the application.** `relayr:proposal-outcome` is among Automation's rules and the code rules (`CODE_RULES`), and the bridge registers its action. Each postmortem people accept, edit or reject scores the `close-incident` run that proposed it.
- **The experiment runs through the application itself.** `incident-scenarios` builds the application with `create_app`, in process, on a scripted model and a SQLite file of its own. It plays each example over its REST API, as monitoring and people would: an alert opens the incident, people write in the thread (and one scenario rewrites the timeline), the incident is resolved, and people accept the postmortem, edit it, or reject it.
- **It measures with relayr's measures,** reading the storage afterwards. Each example's verdict, an `IncidentReview`, reports:
  - the postmortem's outcome, from `proposal_rates`;
  - the timeline's rewrite rate, from evalr's `measure_rewrites` over `relayr.evals.history`;
  - the seconds from the alert to the resolution.
- **Time to resolution is the alert to its resolution, by service.** reflexr's `time_to_resolution` measures a causal chain, and a resolution that monitoring publishes starts a chain of its own, so it can't tell when an incident ended.

## Options considered

| Option | For | Against |
|---|---|---|
| **A postmortem proposed on resolution (chosen)** | A rule's proposal people review, so acceptance and edits are real; a useful artifact | One more rule and artifact type in the example |
| Proposed timeline entries | No new rule | A less useful timeline, with direct and proposed writes in one rule |
| Acceptance from rule drafts (`rule_conversion`) | Nothing new | Measures drafts, not a rule's proposals |
| **The application, over REST (chosen)** | The real wiring, as deployed | Slower than the parts alone |
| The parts, wired anew in the experiment | Faster | A second copy of the wiring, which drifts |

## Consequences

- Easier: `make evals` reports how the example's incidents go, through the same code that serves them.
- Harder: the experiment builds the whole application for each example, so it takes seconds, not milliseconds.
