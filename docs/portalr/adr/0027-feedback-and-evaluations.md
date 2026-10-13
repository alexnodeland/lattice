# ADR-0027: Feedback and evaluations, summed by day, and the first charts

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives admin a Feedback and evaluations area: feedback over time, by workspace and target; evaluation scores and their trend; and links from each to the run it is about. portalr's Langfuse reader read a tenant's scores, newest first, as many as a window's limit allowed, for Home's card. It read only that many of the tenant's traces, and gave no workspace.

Langfuse holds two kinds of score:

- people's feedback, which the libraries mirror;
- evaluators' verdicts, which evalr writes, naming the evaluator in the score's metadata.

The user decided four things:

1. By workspace: a score names its trace's workspace.
2. Charts: Tremor's BarChart, LineChart, DonutChart and Tracker, copied into `ui` on Recharts and restyled, each used for real: the first three here, and Tracker in 6c-iii.
3. Aggregation: portalr sums the scores by day, so a chart is complete at any window.
4. Links: each comment's trace, with Langfuse's page for operators; the in-app trace view comes in 6d.

## Decision

- **A score names its workspace,** from its trace's `workspace:<id>` tag, which artifactr's and reflexr's traces carry. A trace tagged with no workspace, or with two, names none.
- **`GET /portalr/v1/feedback`** sums a window's scores, or one workspace's, for whoever may read the tenant's telemetry. A window ends after it starts and is at most 91 days, or the read is a 422. It answers:
  - `days`: people's thumbs up and down, on each day the window touches, in UTC;
  - `evaluations`: each evaluator's score of each name, with its count, and its count and mean on each day, the most scored first;
  - `workspaces`: each workspace's thumbs and evaluations, the busiest first;
  - `comments`: the 20 newest of what people wrote, each with its trace;
  - `complete`: whether every score was read, false where the read stopped at one of its bounds.
  - It is a reading, as every one is: `ok`, `unavailable` or `unconfigured`.
- **People's feedback is the scores no evaluator gave, that the libraries' feedback mirrors sent,** which Langfuse marks `API`; an annotation made in Langfuse's own UI isn't.
  - A thumb is a yes-or-no one: an application's `thumbs` feedback is mirrored as `thumbs.up`. Langfuse sends a yes-or-no value as 1 or 0, so a thumb is read by its type, its value as true or false.
  - What they wrote is a text one, such as `thumbs.comment`, or a score's comment.
- **An evaluation is an evaluator's score:**
  - a numeric score, as it is;
  - a yes-or-no score, as 1 or 0;
  - averaged per day.
  - Categorical and text scores are counted toward a workspace's evaluations, not averaged.
- **The summary reads every score, within bounds:**
  - The tenant's traces come from Langfuse's observations API, filtered on their tags, and the workspace's if one is named, each checked again, a thousand a page. They are those started up to a week before the window, so a late thumb, or an evaluator's verdict on yesterday's turn, is counted on the day it was given.
  - Their scores in the window come from the score API, newest traces first, fifty traces a request, a hundred scores a page, four requests at once.
  - It stops, and says it is partial, at any of its bounds: 20 pages of traces, 50,000 scores, a cursor that comes round again, or 20 seconds in all. The UI says so, with a badge, and suggests a shorter window or one workspace.
  - Home's card reads the same way, its newest traces first, and stops at its window's limit.
- **Not Langfuse's metrics API.** It sums by day, and filters scores by their traces' tags. But it has no dimension for evalr's evaluator, which is in a score's metadata. So people's feedback and an evaluator's verdict couldn't be told apart.
- **Feedback is `/t/$tenant/feedback`,** on the rail where `portalr:read_telemetry` is allowed. It is gated in `beforeLoad`, as Audit is, and reads in `loader`.
  - Its window, the last 7, 30 or 90 days, and a workspace, are in the address.
  - Its window is whole days in UTC, ending with today's, so a read of it is one query all day, kept ten minutes and tried again once. A score is counted on its day in UTC, and the charts and the windows say "in UTC".
- **The charts:**
  - The thumbs per day are a diverging bar chart: up above the baseline, down below it, each a count. A window with no thumbs says so, rather than draw an empty chart.
  - Each evaluation's mean per day is a line chart, with a gap for a day with none. The three most scored are drawn, and every one is in a table when there are more.
  - People's thumbs by workspace are a donut beside a list of each workspace's count and share, for every workspace; the largest three are drawn, and the rest are folded into "Other".
  - Each workspace's thumbs and evaluations are a table, and people's comments another.
- **`ui`'s charts are Tremor's, adapted,** on Recharts 3:
  - `BarChart`, `LineChart` and `DonutChart` keep only what admin draws.
  - Tremor's Apache-2.0 licence and a NOTICE, naming the commit and what changed, are in `ui`, and in portalr's wheel beside the typefaces' licences, which `ui-in-wheel` checks.
  - Tracker is used in 6c-iii, where a day's spend against its share of the budget is a block.
- **The chart rule (ADR-0021) holds:**
  - The series take the inks in order, `--chart-1` to `--chart-3`, as marks and never as text, three at most.
  - Each pair passes the dataviz palette check in its scheme: lightness, chroma, colour-blind separation, and 3:1 or more on the surface, which a token test holds.
  - Every series is also named in a legend and directly at its last mark, the labels placed from the data and nudged apart before they are drawn, and every chart's figures are a table beneath it.
  - Each series has a pattern: solid, hatched one way, then the other; or a line solid, dashed, then dotted. What is folded into "Other" is dotted in the muted ink.
- **Each comment shows its trace's id.** For an operator, the id is a link to the trace's page in Langfuse, from portalr's deep links, which only operators may read: read once, for a stand-in id, and the trace's own put in its place.
- **The page's weight:** Recharts is in Feedback's own chunk, about 114 kB gzipped, loaded when Feedback is first opened; admin's first load and app's bundle are as they were.
- **The scenario:** the test application runs without Langfuse, so it shows Feedback saying Langfuse isn't configured. The route-level tests cover the rest over a stubbed portalr.

## Options considered

| Option | For | Against |
|---|---|---|
| **Sum in portalr, from every score (chosen)** | Complete at any window; the libraries' meaning of a score kept | Every score read, up to 50,000 |
| Langfuse's metrics API | Langfuse sums | Can't tell people's feedback from an evaluator's verdict |
| Sum in the browser, from the newest 1,000 | No new read | Partial at any busy window |
| Langfuse's metrics API, telling people's feedback by its source or its name's prefix | Langfuse sums | Langfuse marks every library's score `API`, evaluators' too; a name's prefix is the application's to choose |
| **Tremor's components, adapted (chosen)** | Their tooltip, legend and axes, under their licence | Patterns, labels and tokens to add |
| Recharts alone | Less code | Each chart's parts written again |

## Consequences

- Easier: a chart is complete at any window, and a workspace's view is one read.
- Harder: a busy tenant's 90 days are many requests to Langfuse; past a bound, the sums are partial and say so.
