# Rules from chat

A person asks in a thread for something to happen whenever something else does. The chat agent drafts a reflexr rule, a person accepts it, and relayr installs it in reflexr as a stored rule ([ADR-0028](../adr/0028-rules-from-chat.md)).

## Wiring

```python
from relayr.rules import RULES, Installer, RuleDraft, RuleDrafting

stored = StoredRules(actions={"notify": NotifyParams}, namespaces={"chat"})
events = {t.event_type: t for t in [*BRIDGED, *APP_EVENTS]}

collaboration = artifactr.Workspaces(storage, types=[..., RuleDraft])
automation = reflexr.workspace.Workspaces(
    storage, events=events.values(), rules=[*APP_RULES, *RULES], stored_rules=stored
)
chat_agent = Agent(..., capabilities=[ArtifactWorkspace(...), RuleDrafting(automation, events)])
installer = Installer(outbound, collaboration, may_change=may_change)  # or anyone
reactor = Reactor(automation, actions={..., **installer.actions})
```

- **`RuleDraft`** is the `rule` artifact type. Its data is `{rule: Rule}`, and its write policy is `propose`.
- **`RuleDrafting`** gives the chat agent `draft_rule`. It checks drafts against `automation`'s stored rules.
- **`RULES`** holds relayr's code rule, `relayr:rules-from-chat`, and `Installer.actions` holds its action. The rule is scoped by the artifact, so one artifact's changes happen one at a time, in order.

## Drafting

`draft_rule(rule, rationale, artifact_id=None)` does three things:

1. It checks the rule with `check_draft`, which runs reflexr's `Rule.check` and `check_stored`, and hands every problem back to the model to fix. A change of an existing rule's name is refused too.
2. It previews the rule with `preview`, which replays the last week of reflexr's log through the rule and runs nothing. It reads the log as the person the turn acts for, so it counts only what they may read; a turn for no one can't draft.
3. It proposes a new `rule` artifact, or, with `artifact_id`, an edit of one. The rationale ends with "It would have fired N times since …".

## Going live

When a proposal is accepted, `relayr:rules-from-chat` re-reads artifactr. It acts only on what artifactr's own record says:

- The proposal is accepted, and its artifact is a `rule`.
- The artifact is still at the version the acceptance made.
- The person who accepted may install the rule, or update it if the artifact installed one already.

Then it installs the rule, with provenance naming the artifact, its version, the proposal and the person, and posts a notice in the thread: "chat:deploys is live, at version 1."

Archiving the artifact archives the rule, once the rule has checked the same way that the person may archive rules. A forged `artifactr:proposal_resolved` finds no accepted proposal, and installs nothing. An acceptance replayed after it was installed changes nothing, even if an operator has archived its rule in reflexr since.

## Changes made in reflexr

An operator can update or archive a rule from chat in reflexr directly. relayr's `relayr:rule-drift` proposes the same change to the rule's artifact, in the thread it was drafted in ([ADR-0030](../adr/0030-drift-proposed-back-to-a-rules-artifact.md)):

- **An update** is proposed as an edit of the artifact's rule. Accepting it updates the rule from the artifact again.
- **An archive** is proposed as archiving the artifact.
- **Rejecting** leaves reflexr's version running.

Give the outbound adapter relayr's `ALLOWLISTS` with your own, so the drift rule may propose in that thread.

## Who may put a rule live

`may_change(tenant_id, workspace_id, person, change)` decides, and `Installer` requires it. `change` is `install_rule`, `update_rule` or `archive_rule`, reflexr's actions for each. Only a person, a `UserActor`, can put a rule live, never an agent.

- **Without access control,** pass `anyone`.
- **With grantr,** ask whether the person holds `reflexr:<change>` in the workspace. relayr's rule runs as the application, which holds the three actions ([grantr ADR-0027](../../grantr/adr/0027-the-application-installs-the-rules-people-accept.md)), once the application maps relayr's rule among its code rules.

!!! warning "`anyone` lets every person put rules live"

    With `anyone`, every person who can accept a proposal in a workspace can put a rule live there, change it, or archive it. Use it only where every such person may.

## Limits

- An artifact installs one rule. A change of the rule's name is refused: archive it, and draft the new rule apart.
- Only an accepted proposal installs. A person who writes to a `rule` artifact directly installs nothing.
- relayr knows which rule an artifact installed from its own installs, in reflexr's log, never from a stored rule's provenance, which anyone allowed to install can claim.
- A name another artifact installed, and anything reflexr's checks refuse, are reported in a notice, with reflexr's problems.
- Stored rules keep to reflexr's limits: a throttle and a timeout, only the actions `StoredRules` allows, and no predicates ([reflexr RFC-0003](../../reflexr/rfcs/0003-managing-rules-at-runtime.md)).
