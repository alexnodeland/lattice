# ADR-0027: The application installs the rules people accept

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md), which kept rule management out of the `application` role

## Context

relayr's phase 5 turns rules drafted in chat into stored rules ([stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md#rules-from-chat)):

- A person accepts a `rule` artifact's proposal, and the rule is installed; a later accepted change updates it.
- Archiving the artifact archives the rule.

relayr's own code rules are to make those changes in reflexr, after re-reading artifactr. Code rules run as the application ([ADR-0020](0020-the-rule-role.md)), and `application` held no rule management. The people involved hold different actions: an editor holds `artifactr:archive_artifact`, for instance, but not `reflexr:archive_rule`.

## Decision

- **`application` holds `reflexr:install_rule`, `reflexr:update_rule` and `reflexr:archive_rule`** (`RULE_INSTALLS`, in `RUNTIME`), so relayr's rules from chat can change stored rules.
- **relayr checks the person against the matching action for each change.** Before it acts, relayr checks the `UserActor` who accepted the proposal, or archived the artifact. That person must hold the change's own action in the workspace: `install_rule` to install, `update_rule` to update, `archive_rule` to archive. A workspace's admins hold all three, and so do a tenant's owners and admins, and any custom role given them. Only a person, never an agent, puts a rule live.
- **What bounds the grant:**
  - Stored rules are named only in `StoredRules`' namespaces, and can't take a code rule's name ([reflexr ADR-0053](../../reflexr/adr/0053-stored-rules-one-fixed-configuration.md)), so the application can't replace its own code rules this way.
  - The application holds no `respond_to_proposal`, so a person, not the application, decides what is accepted.
  - reflexr's audit shows the application as each change's actor. The provenance relayr records names the person who approved it.
- **relayr's rules must join the template's `CODE_RULES`** before their runs act as the application. Until then, the template maps no actor to it.

## Options considered

| Option | For | Against |
|---|---|---|
| **The three actions in `application` (chosen)** | One grant covers every tenant, as for code rules' other writes | The application's principal can change stored rules in every workspace |
| Install as the person who accepted | grantr checks the person itself | reflexr would log the change as the person's command, not as the run's, so the run's chain and the depth limit wouldn't reach it |
| A role of its own for relayr, granted in each tenant | Only relayr holds it | A grant to make in every tenant, for code that is the application's own |

## Consequences

- Easier: an accepted rule goes live with no grant to make per tenant.
- Harder: whether a person may make a change is checked in relayr before it acts. A bug there would change rules for anyone who can accept a proposal or archive an artifact, so relayr's tests cover that check for each change.
