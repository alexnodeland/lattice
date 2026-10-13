# ADR-0028: Usage and spend, per day and per workspace, against the budget's share

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives admin a Usage and spend area. Each tenant is a LiteLLM team, `tenant-<id>`, and portalr already reads its spend against its budget for Home's card. LiteLLM v1.103 also sums usage by day:

- `/team/daily/activity`, for a team;
- `/tag/daily/activity`, for a request's tags.

Both answer per day, with a breakdown per team or per tag.

A team's activity has no workspace. The user decided two things:

1. **A tenant-scoped tag.** The libraries' LiteLLM gateways also tag each request `tenant-workspace:<tenant>/<workspace>`, through a lattice-core helper that relayr's work adds.
2. **How Usage reads, and its bounds.**
   - It reads the tenant's spend per day from its team.
   - It reads per-workspace spend from the tags of the tenant's own workspaces only, never every tag, checking each answer's tag again, as Feedback does.
   - Its bounds are like Feedback's: a window of at most 91 days, a deadline, kept a while, retried once, and a partial flag.
   - A Tracker shows each day's spend against its share of the team's budget, hidden where there is no budget.

Spend recorded before the tag lands has no workspace, and the page says so, quietly.

## Decision

- **A workspace's tag is `tenant-workspace:<tenant>/<workspace>`**, as `portalr.readers.usage.workspace_tag` builds it. It is agreed with the format relayr's PR gives for lattice-core's helper. Until that PR merges, portalr is built against fixtures in that format.
- **`GET /portalr/v1/usage`**, for whoever may read the tenant's spend (`portalr:read_spend`), takes a window, at most 91 days, and up to 50 `workspaces`. It answers:
  - `days`: the team's spend, tokens and requests on each day the window touches, in UTC, from `/team/daily/activity`, asked for the tenant's team alone;
  - `workspaces`: each named workspace's spend and tokens, over the window and per day, from `/tag/daily/activity`, the most spent first. A workspace with nothing under its tag isn't in it;
  - `budget`: the team's spend and budget, from `/team/info`;
  - `daily_budget`: a day's share of the budget;
  - `complete`: false where the read stopped at one of its bounds.
  - It is a reading, as every one is: `ok`, `unavailable` or `unconfigured`.
- **Only the tenant's own tags are asked for**: those of the workspaces the request names, which admin takes from artifactr's list of the tenant's workspaces. The read never lists every tag. Each tag in an answer is kept only if it is one the read asked for, and each team only if it is the tenant's, so another tenant's workspace of the same name is never counted.
- **A day's share of the budget** is the team's `max_budget` over its `budget_duration` in days, read as LiteLLM reads a duration: seconds, minutes, hours, days, weeks or months, or `hourly`, `daily`, `weekly` or `monthly`, with a month taken as 30 days. With no budget, a budget of 0, or a duration that can't be read, there is no share, and none is guessed.
- **The read is bounded**, as Feedback's is:
  - The team's activity, the tags' and the budget are read at once, 1,000 records a page, up to 20 pages each. A day split across two pages, as LiteLLM pages its rows before grouping them by day, is summed.
  - Past 20 pages, the read is partial.
  - A refused read cancels the others, and the whole read is unavailable.
  - At 20 seconds, it answers what it has, partial. If not a page of the team's activity has been read by then, it is unavailable, "litellm didn't answer in time", rather than a window of zeros. A budget not yet read is none, so the Tracker is hidden.
  - admin keeps a read ten minutes, and tries it again once, unless it was refused outright.
- **Usage is `/t/$tenant/usage`**, on the rail where `portalr:read_spend` is allowed. It is gated in `beforeLoad` and reads in `loader`.
  - Its window, the last 7, 30 or 90 days in UTC, is in the address, as Feedback's is.
  - The workspaces to split by are the tenant's from artifactr, in order, at most 50. If artifactr refuses the list, the spend is read whole, and the page says so. Where there are more than 50, it says only the first 50 are split out.
- **The page:**
  - It shows the window's spend and requests, and the spend per day as a bar chart.
  - Where the team has a budget with a share, a Tracker shows each day against that share: nothing spent, under it, near it (80% or more), or over it.
  - Each workspace's part is a donut, with what no workspace's tag holds as "No workspace", and every workspace is in a table.
  - Beneath, quietly: "Spend recorded before the libraries tagged each request with its workspace has no workspace split, and is counted under 'No workspace'."
- **`ui`'s Tracker is Tremor's, adapted**, as the charts are (ADR-0027), and the NOTICE names it.
  - Its blocks take a level each, in the kit's tokens: the muted line, then the inks. Past the second level, a block has a pattern too, striped then hatched, so colour is never its only cue (ADR-0021).
  - Each level is named in a legend, and each block in a title, where Tremor has a hover card.
  - Its figures are a table beneath it.
  - Recharts stays out of admin's entry, which admin's build checks.
- **The scenario:** the test application runs without LiteLLM, so it shows Usage saying LiteLLM isn't configured. The route-level tests cover the rest over a stubbed portalr.

## Options considered

| Option | For | Against |
|---|---|---|
| **A tenant-scoped tag, asked for by name (chosen)** | A workspace's spend from LiteLLM's own sums; another tenant's never asked for | Spend before the tag lands has no workspace |
| The bare `workspace:<id>` tag | Already on traces | A workspace's id is unique only in its tenant: another tenant's would be counted |
| Every tag, filtered in portalr | No list of workspaces needed | Reads every tenant's tags |
| Per-workspace spend from Langfuse's traces | Has the workspace | Not LiteLLM's spend, which the budget is in |
| **A day's share, as LiteLLM reads the duration (chosen)** | The same sums LiteLLM resets the budget by | A month taken as 30 days |

## Consequences

- Easier: a tenant sees what each workspace spent, from the same sums LiteLLM budgets by, and each day against its share.
- Harder: until the gateways send the tag, no spend has a workspace. A workspace past the first 50 is under "No workspace".
