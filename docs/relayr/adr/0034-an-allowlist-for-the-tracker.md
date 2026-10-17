# ADR-0034: An allowlist for the tracker

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Amends [ADR-0020](0020-allowlists.md), as [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md#what-a-rule-does) proposes.

## Context

A rule's allowlist says what it may do beyond proposals and notices in artifactr. RFC-0004 lets a rule's run write to its workspace's tracker, which reaches people outside the chat, and nothing should do so by omission.

## Decision

- **`Allowlist` gains `trackers: bool`, false by default.** A rule writes to its workspace's tracker, by `TrackerActions` or `TrackerCapability`, only if it is set; otherwise every write is `NotAllowed`. The model stays frozen, and an allowlist written before reads as it did.
- **`Trackers` takes the same allowlists as `Outbound`,** by a rule's name or its namespace's (`"ops:*"`, [ADR-0029](0029-an-allowlist-for-a-whole-rule-namespace.md)), through the lookup both now share, `Allowlists`.
- **A bool, not reads and writes apart.** Rules will read the tracker through its events (RFC-0004's phase 2), so v1 doesn't tell reading from writing; `read` and `filed` need the permission too.

## Consequences

- The allowlist still says, in one line beside each rule, everything it may do; a rule nobody allowed files nothing.
- A finer split, by project or by operation, would be a new field.
