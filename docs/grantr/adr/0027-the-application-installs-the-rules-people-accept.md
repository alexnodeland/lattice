# ADR-0027: The application installs the rules people accept

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md), which kept rule management out of the `application` role

## Context

relayr's phase 5 turns rules drafted in chat into stored rules ([stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md#rules-from-chat)). A person accepts a `rule` artifact's proposal. relayr's own code rule, `relayr:install-rule`, then re-reads artifactr and checks that the person may install rules. With grantr, that check is whether the person holds `reflexr:install_rule` in the workspace. Then it installs, updates or archives the stored rule in reflexr. Code rules run as the application ([ADR-0020](0020-the-rule-role.md)), and `application` held no rule management.

## Decision

- **`application` holds `reflexr:install_rule`, `reflexr:update_rule` and `reflexr:archive_rule`** (`RULE_INSTALLS` in `RUNTIME`), so relayr's `install-rule` run can change stored rules.
- **The person is checked in relayr, not here.** Before it installs, relayr checks that the person who accepted holds `reflexr:install_rule` in the workspace, which only admins do. The application acts on that person's decision.
- **It still holds no `respond_to_proposal`:** a person accepts a rule, never the application.

## Options considered

| Option | For | Against |
|---|---|---|
| **The three actions in `application` (chosen)** | One grant covers every tenant, as for code rules' other writes | The application's principal can change stored rules in every workspace |
| Install as the person who accepted | grantr checks the person itself | reflexr would log the change as the person's command, not as the run's, so the run's chain and the depth limit wouldn't reach it |
| A role of its own for relayr, granted in each tenant | Only relayr holds it | A grant to make in every tenant, for code that is the application's own |

## Consequences

- Easier: an accepted rule goes live with no grant to make per tenant.
- Harder: whether a person may install a rule is checked in relayr before it acts. A bug there would install rules for anyone who can accept a proposal, so relayr's tests have to cover that check.
