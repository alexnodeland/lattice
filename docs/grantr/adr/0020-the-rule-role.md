# ADR-0020: The rule role

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

A stored rule's runs act as its principal, `RulePrincipal`, which holds nothing until it is granted a role ([ADR-0004](0004-an-agent-turn-acts-for-its-user.md)). Whoever installs the rule grants it, and no one grants more than they hold ([ADR-0010](0010-commands-bounded-by-what-their-maker-holds.md)). A rule's run publishes events, checkpoints itself, and reads what its actions read. Rules defined in code are the application's, and run as its principal.

## Decision

- **A built-in `rule` role** holds `reflexr:open`, `reflexr:publish`, `reflexr:checkpoint_run` and reflexr's reads, but its cursors. It is granted on a workspace, or on the rule itself.
- **A workspace's `admin` holds every action of `rule`,** `checkpoint_run` included, so an admin who installs a rule can grant it its role.
- **A rule defined in code runs as the application's principal,** and holds what [ADR-0019](0019-runtime-actions-and-the-application-role.md)'s `application` holds; `RulePrincipal` is for stored rules.

## Options considered

| Option | For | Against |
|---|---|---|
| **A built-in `rule` role (chosen)** | Every installer grants the same, reviewed set | A rule that needs more needs a custom role |
| A custom role per application | Each application decides | Every application writes the same role, and the matrix can't show it |

## Consequences

- Easier: relayr's install rule (stackr RFC-0002) grants one role, and a workspace's admin may give it.
- Harder: a rule whose actions write in artifactr needs more than `rule`, granted separately.
