# ADR-0054: Installing, updating and archiving stored rules

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Decided on [RFC-0003](../rfcs/0003-managing-rules-at-runtime.md).

## Context

[ADR-0053](0053-stored-rules-one-fixed-configuration.md) decides what a stored rule may be. This record decides how one changes: the commands, what each keeps, and how a rule stops. stackr RFC-0002's D5 makes the artifact a person accepted the reviewed record and reflexr's store the running definition, with drift noticed both ways, so every change needs a version and a record of where it came from.

reflexr already has what a change needs: core's `begin` and `reset`, generations and `reflexr:rule_reset`, `replay_rule`, the one command entry point, and `due_runs` with its `RunPolicy`.

## Decision

- **Three commands,** carried out by `Workspaces.execute` like every other ([ADR-0047](0047-commands-carried-out-once-per-id.md)), and `Workspace` methods in process:

| Command | Fields | Does |
|---|---|---|
| `install_rule` | `rule`, `provenance?` | Version 1, or the next version of an archived rule. An active rule of that name is `invalid_state` |
| `update_rule` | `rule`, `expected_version?`, `provenance?` | The next version of an active rule, reset if its definition changed |
| `archive_rule` | `rule` (the name), `expected_version?`, `reason?` | Archives it, and cancels its unfinished runs |

- **Each answers `rule_version`:** `{rule, version, seq, duplicate}`, where `seq` is the change's fact.
- **One row per rule, with the log as its history.** Storage keeps each rule's current version in `reflexr_rules` (migration 0006). Every change is a new version, numbered from 1 per workspace and name, and a `reflexr:rule_installed` fact carries the whole rule and its provenance; archiving appends `reflexr:rule_archived`. Rolling back is updating to an earlier version's rule.
- **A change takes the workspace's lock,** as a publish does, so it is atomic with its fact and the rule's progress, and serialized with evaluation. It needs no new lease.
- **Resets as code rules reset.** `begin` and `reset` run in the change's transaction, so a rule starts at its own fact, and an update that changes its condition or scope (`Rule.definition()`) resets it there, with `reflexr:rule_reset` after `reflexr:rule_installed`. A rule installed again after it was archived is reset too, continuing its generation, so it never reuses a firing id.
- **No replay on install.** `start` is `now`. `replay_rule` works on a stored rule as on a code rule, for anyone who wants it warm.
- **A run executes the current version,** read when it is claimed, as for code rules.
- **Duplicates and conflicts.** A change whose result equals the current version appends nothing and answers `duplicate: true`. That is checked before `expected_version`, so a retry of a change that succeeded is a duplicate, not a conflict. `expected_version` is optimistic concurrency: a rule at another version is `invalid_state`, naming its version.
- **Provenance is an opaque JSON map,** at most 4 KiB, kept on the row and on each fact. reflexr doesn't read it. Who made the change is the envelope's actor.
- **Archiving is the only way to stop.** Stored rules are always enabled, unordered and never block on a dead letter, so `due_runs`, `RunPolicy` and their schema stay as they are: a rule the policy doesn't name has all its due runs returned, which is right for an unordered, enabled rule. Archiving cancels the rule's unfinished runs with core's `cancel` and clears its scope states, in its own transaction. Its progress row stays.

## Options considered

### Commands

| Option | For | Against |
|---|---|---|
| **Three: `install_rule`, `update_rule`, `archive_rule` (chosen)** | Each change is what it is, on every surface | Changing a rule means sending it whole |
| Five, with `disable_rule` and `enable_rule` | Pause without archiving | Stopping state, and the parts of `due_runs` that serve it |
| One upsert | One command | An update meant for an existing rule silently creates one |
| REST resources | Familiar | A second path beside the commands |

### Stopping

| Option | For | Against |
|---|---|---|
| **Archive only: stored rules always enabled, unordered, never blocking (chosen)** | `due_runs`, `RunPolicy` and their schema stay as they are | No pause, and a scope's runs may overlap |
| Disable and enable | Pause and resume | `due_runs` would join stored rules to learn which are disabled |
| Ordered stored rules | A scope's runs in firing order | The same join, to keep the scope-head fix |

### History

| Option | For | Against |
|---|---|---|
| **One row per rule, with the facts as history (chosen)** | Reads are one primary-key lookup, and the log already holds every version | A version's history is read from the log |
| Rules only in the log, with no table | Nothing new to store | Every pass would scan logs to find a workspace's rules |
| A table of every version | History without the log | A second record of what the facts say, needed only once retention compacts logs |

## Consequences

- Easier: relayr installs with provenance, updates with `expected_version`, and retries any change safely.
- Easier: a rule installed while reactors serve fires on the next matching event, even one published before either's next pass, since the change and evaluation take the same lock.
- Harder: a stored rule can't pause; archiving and installing again is the way, and it starts afresh.
- Harder: downgrading migration 0006 drops every stored rule. Their facts stay in the logs.
- To revisit: a table of every version, and recording the fired version on each run, once retention compacts logs.

## Action items

1. [x] `reflexr_rules`, in memory and in SQL, with migration 0006 (alexnodeland/reflexr#87).
2. [x] The three commands, their facts and `rule_version`, carried out by `execute` (alexnodeland/reflexr#88).
3. [x] The MCP tools for the three commands (alexnodeland/reflexr#89).
