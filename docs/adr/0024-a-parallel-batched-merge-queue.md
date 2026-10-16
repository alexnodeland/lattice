# ADR-0024: A parallel, batched merge queue

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Amends [ADR-0016](0016-a-merge-queue-on-mergify.md), whose "Revisit" this answers: batching and parallel checks, once the queue is the bottleneck.

## Context

ADR-0016's queue is serial and in place: Mergify updates the pull request with `main`, waits for a fresh `CI`, merges, and only then starts the next. Over the 40 pull requests merged from 2026-10-13 to 2026-10-16 (measured with `gh`), the time from the `queue` label to the merge had a median of 10.8 minutes and a 90th percentile of 48 (maximum 114), the final `CI` run a median of 9.9 minutes (maximum 19.2), and consecutive merges were 15 to 20 minutes apart in a busy stretch: three or four pull requests an hour, and 45 to 75 minutes for the fourth in a queue. `CI`'s 30-odd jobs run in parallel, so a run lasts about as long as its slowest job (6 to 8 minutes, the Smoke jobs, tier 2 and Acceptance); what is slow is that each pull request pays that cycle alone, and in series. Every pull request also ran `CI` twice, once on its own pushes and again after Mergify updated it.

The ruleset required branches to be up to date (`strict_required_status_checks_policy`), which is what forced one pull request at a time.

## Decision

- **Mergify tests the queue in draft pull requests,** with up to two checks at once (`max_parallel_checks: 2`) and batches of one to three pull requests (`batch_size: {min: 1, max: 3}`): one when the queue is short, more as it backs up, waiting at most two minutes for a batch to fill (`batch_max_wait_time`). A batch's draft pull request holds the batched pull requests on top of `main` and of the batches ahead of it, so what is tested is what will be on `main`.
- **A batch passes on `CI`,** the only `merge_condition`: it is evaluated on the draft pull request. `Title` is still a required check of the pull request itself, and a condition of entering the queue (Mergify adds the ruleset's required checks), but it is skipped on Mergify's draft pull requests (`title.yml`), whose titles are Mergify's.
- **The ruleset no longer requires branches to be up to date** (`strict_required_status_checks_policy: false`). A pull request's checks are those of its batch against the `main` of the moment, not of its own head. This is the user's setting, not the repository's file.
- **A batch that fails is split and tested again** until the pull request that broke it is found; it is taken out of the queue with a comment from Mergify saying so, and the others merge. Pull requests behind a failed batch are tested again on top of what is left.
- **Pull requests are squash-merged one at a time,** each with its own title, as before.

## Consequences

- Easier: a queue of four clears in about 10 to 20 minutes instead of 45 to 75, and CI minutes fall in a busy stretch, since one run covers a batch. A lone pull request is as quick as before.
- Harder: a pull request's green `CI` no longer proves its own head on the latest `main`; the batch's does. A failure in a batch can be a neighbour's, and a failed batch costs reruns.
- Order and rollback: the ruleset and `.mergify.yml` change independently. With the up-to-date requirement still on, batches could not merge; with it off and the old `.mergify.yml`, the serial queue still works. To go back, set the ruleset's "Require branches to be up to date before merging" on again, and revert the pull request that made this change.
