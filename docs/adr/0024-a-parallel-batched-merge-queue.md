# ADR-0024: A parallel, batched merge queue

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Amends [ADR-0016](0016-a-merge-queue-on-mergify.md), whose "Revisit" this answers: batching and parallel checks, once the queue is the bottleneck.

## Context

ADR-0016's queue was serial and in place, because the ruleset required branches to be up to date: Mergify updated one pull request with `main`, waited for a fresh `CI`, merged it, and only then started the next. `CI`'s jobs run in parallel and a run lasts about ten minutes, so what was slow was that each pull request paid that cycle alone: three or four merges an hour, and 45 to 75 minutes for the fourth pull request in a queue. The figures are from the last 40 pull requests merged (2026-10-13 to 2026-10-16), read with `gh`: the time from the `queue` label's timeline event to `mergedAt` (median 10.8 minutes, 90th percentile 48, maximum 114; 30 had a label event), and the final `CI` run of each head (median 9.9 minutes, maximum 19.2).

## Decision

- **Mergify tests the queue in draft pull requests,** two checks at once (`max_parallel_checks: 2`) and batches of one or two pull requests (`batch_size: {min: 1, max: 2}`): one when the queue is short, two as it backs up, waiting at most thirty seconds, Mergify's default, for a batch to fill (`batch_max_wait_time`), so a lone pull request is not held back. The maximum is raised after a week of queue statistics, up to three. A batch's draft pull request holds its pull requests on top of `main` and of the batches ahead of it, so what is tested is what will be on `main`.
- **A batch passes on `CI`,** the one `merge_condition`, evaluated on the draft pull request. `Title` is still a required check of each pull request, and a condition of entering the queue. It runs on the draft pull requests too and concludes success without checking them, whose titles are Mergify's (`title.yml`): its steps, not its job, are skipped, since a skipped job is not a success to the required checks Mergify counts. They are skipped only for a pull request Mergify's App opened, in this repository, on a branch of the queue's, so a fork cannot name a branch to escape the title and public-API checks; the pull requests in the batch passed both, and each is squash-merged with its own title and description (`commit_message_format`).
- **The ruleset no longer requires branches to be up to date** (`strict_required_status_checks_policy: false`). A pull request's checks are those of its batch against the `main` of the moment, not of its own head. This is the user's setting, made separately.
- **A batch that fails is bisected.** Mergify splits it into `max_parallel_checks` parts (two: binary bisection), tests them, merges the part that passes and splits the one that fails, until a single pull request fails. That one is taken out with a comment from Mergify, and the pull requests behind it are tested again without it. `batch_max_failure_resolution_attempts: 3` caps the splitting. Two pull requests that conflict with each other in one batch are not bisected: the draft pull request cannot be made, and Mergify takes them out with a comment.

## Consequences

- Easier: a queue of four should clear in about 10 to 20 minutes instead of 45 to 75, and CI minutes fall in a busy stretch, since one run covers a batch. A lone pull request is as quick as before.
- Harder: a pull request's green `CI` no longer proves its own head on the latest `main`; the batch's does. A failure in a batch can be a neighbour's, and a failed batch costs reruns.
- Rollback: the ruleset and `.mergify.yml` change independently, and reverting only `.mergify.yml` is safe with the up-to-date requirement on or off. To go back to the serial queue, revert the pull request that made this change, and turn the ruleset's "Require branches to be up to date before merging" back on; the second is the user's. The `Title` workflow's skip is harmless without batches.
- Not tested before it merged: only Mergify can make a batch. The first two pull requests queued after it are its test.
