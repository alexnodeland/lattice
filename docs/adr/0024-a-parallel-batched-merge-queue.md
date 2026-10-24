# ADR-0024: A parallel, batched merge queue

**Status:** Accepted, amended 2026-10-16 and 2026-10-24 (see Amendments)
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Amends [ADR-0016](0016-a-merge-queue-on-mergify.md), whose "Revisit" this answers: batching and parallel checks, once the queue is the bottleneck.

## Context

ADR-0016's queue was serial and in place, because the ruleset required branches to be up to date: Mergify updated one pull request with `main`, waited for a fresh `CI`, merged it, and only then started the next. `CI`'s jobs run in parallel and a run lasts about ten minutes, so what was slow was that each pull request paid that cycle alone: three or four merges an hour, and 45 to 75 minutes for the fourth pull request in a queue. The figures are from the last 40 pull requests merged (2026-10-13 to 2026-10-16), read with `gh`: the time from the `queue` label's timeline event to `mergedAt` (median 10.8 minutes, 90th percentile 48, maximum 114; 30 had a label event), and the final `CI` run of each head (median 9.9 minutes, maximum 19.2).

## Decision

- **Mergify tests the queue in draft pull requests (until 2026-10-24, see the amendments),** two checks at once (`max_parallel_checks: 2`) and batches of one or two pull requests (`batch_size: {min: 1, max: 2}`): one when the queue is short, two as it backs up, waiting at most thirty seconds, Mergify's default, for a batch to fill (`batch_max_wait_time`), so a lone pull request is not held back. The maximum is raised after a week of queue statistics, up to three. A batch's draft pull request holds its pull requests on top of `main` and of the batches ahead of it, so what is tested is what will be on `main`.
- **A batch passes on `CI`,** the one `merge_condition`, evaluated on the draft pull request. `Title` is still a required check of each pull request, and a condition of entering the queue. It runs on the draft pull requests too and concludes success without checking them, whose titles are Mergify's (`title.yml`): its steps, not its job, are skipped, since a skipped job is not a success to the required checks Mergify counts. They are skipped only for a pull request Mergify's App opened, in this repository, on a branch of the queue's, so a fork cannot name a branch to escape the title and public-API checks; the pull requests in the batch passed both, and each is squash-merged with its own title and description (`commit_message_format`).
- **The ruleset no longer requires branches to be up to date** (`strict_required_status_checks_policy: false`). A pull request's checks are those of its batch against the `main` of the moment, not of its own head. This is the user's setting, made separately.
- **A batch that fails is bisected.** Mergify splits it into `max_parallel_checks` parts (two: binary bisection), tests them, merges the part that passes and splits the one that fails, until a single pull request fails. That one is taken out with a comment from Mergify, and the pull requests behind it are tested again without it. `batch_max_failure_resolution_attempts: 3` caps the splitting. Two pull requests that conflict with each other in one batch are not bisected: the draft pull request cannot be made, and Mergify takes them out with a comment.

## Consequences

- Easier: a queue of four should clear in about 10 to 20 minutes instead of 45 to 75, and CI minutes fall in a busy stretch, since one run covers a batch. A lone pull request is as quick as before (until 2026-10-24: see the last amendment).
- Harder: a pull request's green `CI` no longer proves its own head on the latest `main`; the batch's does. A failure in a batch can be a neighbour's, and a failed batch costs reruns.
- Rollback: the ruleset and `.mergify.yml` change independently, and reverting only `.mergify.yml` is safe with the up-to-date requirement on or off. To go back to the serial queue, revert the pull request that made this change, and turn the ruleset's "Require branches to be up to date before merging" back on; the second is the user's. The `Title` workflow's skip is harmless without batches.
- Not tested before it merged: only Mergify can make a batch. The first two pull requests queued after it are its test.

## Amendment (2026-10-16)

The maximum was to be raised after a week of queue statistics; it is raised now, on the evidence in hand. The CI flake that made a failed batch likely is fixed (#256), and under the strict policy the fourth pull request in a queue still waited 45 to 75 minutes.

- **Three checks at once** (`max_parallel_checks: 3`) and **batches of one to five** (`batch_size: {min: 1, max: 5}`). The minimum and `batch_max_wait_time` (thirty seconds) are unchanged.
- **`batch_max_failure_resolution_attempts` stays 3.** A failed batch is split into `max_parallel_checks` parts, so five pull requests split in three parts (two, two, one) leave a failing part of at most two, and one more split isolates the culprit: ceil(log3(5)) = 2 splits, within the cap of 3.
- The Decision above is otherwise unchanged; the numbers it gives for checks and batch size are superseded by these.

## Amendment (2026-10-24)

The queue's time is bound by runner slots, not compute. Over 40 merged pull requests in two days, a pull request spent a median 34 minutes in the queue (90th percentile 68), and 17 of 57 entries ended in a dequeue instead of a merge. A `CI` run is 39 jobs and GitHub runs 20 at once; with a 30-second window, 23 of the 24 drafts seen held one pull request, so three drafts of 39 jobs competed for 20 slots, jobs waited 11 to 17 minutes for a runner, and a failed first draft discarded the ones stacked on it.

- **Two checks at once** (`max_parallel_checks: 2`), **batches of one to five** (`batch_size: {min: 1, max: 5}`, unchanged), and **a three-minute window** (`batch_max_wait_time: 3 minutes`). Mergify's docs say a dynamic batch stays at its minimum while the parallel checks can drain the queue and grows toward the maximum when the queue outpaces them: with two checks, a backed-up queue shares drafts, which is when it saves the most, and a lone pull request meets the minimum of one, so it is expected not to wait for the window.
- **A minimum of two is the option for later.** It would make a burst of labels one draft sooner, but the docs describe the wait as a ceiling counted from the first pull request to enter a batch and do not say what a lone pull request does below the minimum: it could wait for a second with no sign. Try it after watching real batches under these settings.
- **`checks_timeout: 90 minutes`**, not `auto`. `auto` is computed from the queue's recent CI runtime, the 95th percentile and a margin the docs don't state; a draft waiting for runners ran 31 minutes at the median and 56 at the longest, a batch of five can run longer, and tier 2's gate and job can take 80 between them. Drop it for `auto` once the queue has history under these settings.
- **`batch_max_failure_resolution_attempts` stays 3.** A failed batch is split into two parts, so five pull requests need at most ceil(log2(5)) = 3 rounds, which the cap allows (the docs don't define a round precisely). A failed batch of five costs more rounds than with three parts, which is the price of the smaller slot budget.
- **Rollback:** restore `batch_size.min`, `batch_max_wait_time` and `max_parallel_checks` to 1, 30 seconds and 3, and remove `checks_timeout`.
- The Decision above is otherwise unchanged; its numbers are superseded by these and the 2026-10-16 ones.
