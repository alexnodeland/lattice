# ADR-0029: A stored rule acts as itself, in its own workspace

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:**

- [ADR-0020](0020-the-rule-role.md): an admin no longer grants a stored rule its role by hand.
- [ADR-0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md): it left stored rules "an artifactr-side role granted apart".

## Context

A rule drafted in chat runs as a stored rule ([stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md#rules-from-chat)). Its first action, `notify`, posts a notice in a thread its drafter named. The notice goes through relayr's outbound adapter, as the rule's own actor in artifactr. The template checks a stored rule's actors as its `RulePrincipal`, in reflexr and in artifactr ([ADR-0028](0028-a-principals-id-cant-pass-for-the-libraries-actors.md)).

Two things stood in its way:

- **The role had to be granted by hand.** A `RulePrincipal` held only what it was granted, and [ADR-0020](0020-the-rule-role.md) had an admin who installs a rule grant it `rule`. relayr installs rules from chat on a person's acceptance, so no admin is at hand to make that grant.
- **The role held nothing in artifactr.** So the notice would be refused even once granted.

## Decision

- **A `RulePrincipal(workspace, rule)` holds `rule` in its own workspace, with no grant, and nowhere else.** grantr adds that role to the principal's grants whenever it checks one, lists what it may act on, or works out what it can't see.
- **The `rule` role also holds `artifactr:open` and `artifactr:post_message`,** so a stored rule's run can open its workspace in artifactr and post its notices there. Without reflexr's catalog, `rule` holds nothing, since stored rules are reflexr's.
- **A rule principal is granted nothing beyond its own workspace, and no role that manages access.** A grant to one on another workspace or on the tenant is refused, and so is any role that holds a `grantr:` action, such as a workspace's `admin` or a custom role with `grantr:restrict`: a rule never needs to manage access. A stored grant to one outside its workspace, from before these were refused, counts for nothing when grantr checks it.
- **Why holding it without a grant is safe:**
  - Only an active stored rule runs, and only someone allowed to install rules in that workspace put it there: a workspace's admin, or relayr's install rule acting on such a person's acceptance ([ADR-0027](0027-the-application-installs-the-rules-people-accept.md)).
  - No key can pass for a rule. A principal's id can't hold a `:` ([ADR-0028](0028-a-principals-id-cant-pass-for-the-libraries-actors.md)), so only the libraries' own rule actors map to a `RulePrincipal`.
  - grantr trusts the principal's `(workspace, rule)` pair, so the integration must build it from the workspace the run is in. The template does so from the workspace each check is asked in, and relayr opens only the run's own workspace in artifactr, as the rule's actor ([relayr ADR-0022](../../relayr/adr/0022-what-a-rules-actor-needs-in-artifactr.md)).
- **Restricted items stay out of reach.** The `rule` role is held around a thread, never on it, and holds no `grantr:restrict`. So a stored rule can't post into a restricted thread, or see it. Since a rule can't be granted a role that manages access, the only way it gets into a restricted thread is a role granted on that thread itself, in its own workspace, by someone who chose to.
- **It holds nothing else in artifactr:** no artifact writes, no proposals, and no reads beyond opening the workspace. relayr's allowlist for the rule limits it further, to notices ([relayr ADR-0020](../../relayr/adr/0020-allowlists.md)).
- **That allowlist must keep `turns=False`.** A turn a rule's message started acts for the rule: the template checks its `AgentActor(on_behalf_of=<the rule's actor>)` as the rule's principal. A rule from chat that could start turns would lend its role to an agent.

## Options considered

| Option | For | Against |
|---|---|---|
| **The `rule` role held implicitly, with artifactr's open and post (chosen)** | No grant to keep in step with installs and archives; least privilege; restricted threads stay out of reach | One role now spans two libraries |
| A separate artifactr-side role, granted apart, as ADR-0025 planned | Each library's grant is its own | Two grants to make and revoke per rule, and nothing to make them when a person's acceptance installs it |
| relayr grants the role on install, as the approving person | grantr's grants stay explicit | The person also needs `grantr:grant`, so a custom role with only `install_rule` would install a rule that can't run |
| A stored rule checked as the application | No grantr change | A rule a person drafted would borrow the application's artifactr powers in every tenant, and pass restricted threads |

## Consequences

- Easier: a rule installed from chat, or by an admin, runs without a grant, and can tell a thread what it saw.
- Harder: an action stored rules may run that writes more than a notice needs its own grant here first.
- Harder: the `rule` role's actions are what every stored rule holds, so widening them widens every stored rule at once.
- Harder: revoking no longer stops a rule, since no grant gave it its role. Archiving it does.
