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
chat_agent = Agent(..., capabilities=[ArtifactWorkspace(...), RuleDrafting(automation, events, stored)])
installer = Installer(outbound, collaboration, may_change=may_change)
reactor = Reactor(automation, actions={..., **installer.actions})
```

- **`RuleDraft`** is the `rule` artifact type. Its data is `{rule: Rule}`, and its write policy is `propose`.
- **`RuleDrafting`** gives the chat agent `draft_rule`.
- **`RULES`** are relayr's two code rules, `relayr:install-rule` and `relayr:archive-rule`, and `Installer.actions` are their actions.

## Drafting

`draft_rule(rule, rationale, artifact_id=None)` does three things:

1. It checks the rule with `check_draft`, which runs reflexr's `Rule.check` and `check_stored`, and hands every problem back to the model to fix.
2. It previews the rule with `preview`, which replays the last week of reflexr's log through the rule and runs nothing.
3. It proposes a new `rule` artifact, or, with `artifact_id`, an edit of one. The rationale ends with "It would have fired N times since …".

## Going live

When a proposal is accepted, `relayr:install-rule` re-reads artifactr. It acts only on what artifactr's own record says:

- The proposal is accepted, and its artifact is a `rule`.
- The artifact is still at the version the acceptance made.
- The person who accepted may install the rule, or update it if the artifact installed one already.

Then it installs the rule, with provenance naming the artifact, its version, the proposal and the person, and posts a notice in the thread: "chat:deploys is live, at version 1."

Archiving the artifact archives the rule, once `relayr:archive-rule` has checked the same way that the person may archive rules. A forged `artifactr:proposal_resolved` finds no accepted proposal, and installs nothing.

## Who may put a rule live

`may_change(tenant_id, workspace_id, person, change)` decides. `change` is `install_rule`, `update_rule` or `archive_rule`, reflexr's actions for each. Only a person, a `UserActor`, can put a rule live, never an agent.

- **Without `may_change`,** any person may, as without access control.
- **With grantr,** ask whether the person holds `reflexr:<change>` in the workspace. relayr's rules run as the application, which holds the three actions ([grantr ADR-0027](../../grantr/adr/0027-the-application-installs-the-rules-people-accept.md)), once the application maps relayr's rules among its code rules.

## Limits

- An artifact installs one rule. A change of the rule's name is refused: archive it, and draft the new rule apart.
- A name another artifact installed, and anything reflexr's checks refuse, are reported in a notice, with reflexr's problems.
- Stored rules keep to reflexr's limits: a throttle and a timeout, only the actions `StoredRules` allows, and no predicates ([reflexr RFC-0003](../../reflexr/rfcs/0003-managing-rules-at-runtime.md)).
