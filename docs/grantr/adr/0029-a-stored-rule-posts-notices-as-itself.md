# ADR-0029: A stored rule posts notices as itself

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md), which left stored rules "an artifactr-side role granted apart"

## Context

A rule drafted in chat runs as a stored rule ([stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md#rules-from-chat)). Its first action, `notify`, posts a notice in a thread its drafter named, through relayr's outbound adapter, as the rule's own actor in artifactr. grantr checks a stored rule's reflexr actor as its `RulePrincipal`, which holds the `rule` role ([ADR-0020](0020-the-rule-role.md)). That role held nothing in artifactr, so the notice would be refused. Code rules post as the application, which holds artifactr's writes in every tenant ([ADR-0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md)).

## Decision

- **The `rule` role holds `artifactr:open` and `artifactr:post_message`,** so a stored rule's run can open its workspace in artifactr and post its notices there.
- **A stored rule's artifactr actor is checked as its `RulePrincipal`,** as its reflexr actor is, not as the application. The template does so already ([ADR-0028](0028-a-principals-id-cant-pass-for-the-libraries-actors.md)).
- **Restricted items stay restricted.** The `rule` role holds no `grantr:restrict`, so a stored rule can't post into a restricted thread unless it is granted there ([ADR-0024](0024-who-sees-a-restricted-item.md)).
- **It holds nothing else in artifactr:** no artifact writes, no proposals, and no reads beyond opening the workspace. relayr's allowlist for the rule's namespace limits it further, to notices.

## Options considered

| Option | For | Against |
|---|---|---|
| **Posting in the `rule` role, checked as the rule (chosen)** | Least privilege, and restricted threads stay out of reach | One more grant to the `rule` role |
| A stored rule checked as the application | No grantr change | A rule a person drafted would borrow the application's artifactr powers in every tenant, and pass restricted threads |
| A role per stored rule, granted at install | Each rule holds only what its own actions need | A grant to make and revoke with every install and archive |

## Consequences

- Easier: a rule drafted in chat can tell a thread what it saw.
- Harder: an action stored rules may run that writes more than a notice needs its own grant here first.
