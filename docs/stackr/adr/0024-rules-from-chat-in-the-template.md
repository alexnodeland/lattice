# ADR-0024: Rules from chat in the template

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the template's part of phase 5 of [relayr RFC-0001](../../relayr/rfcs/0001-v0.1-implementation-plan.md), as [stackr RFC-0002](../rfcs/0002-the-combined-system.md#rules-from-chat) designs it, on relayr's rules from chat ([relayr ADR-0028](../../relayr/adr/0028-rules-from-chat.md)).

## Context

relayr turns a rule drafted in a thread into a stored rule in reflexr, once a person who may install rules accepts it. The template's bridge ([ADR-0021](0021-the-bridge-in-the-template.md)) had no stored rules: no namespace for them, no action they may run, and no drafting tool.

## Decision

- **Stored rules live in the `chat` namespace, and run only `notify`** (`chat_rules.py`). `notify` posts a notice in the thread a rule names, with the rule's name and description. reflexr's limits apply: a throttle, a timeout, and no code.
- **`chat:*` gets `Allowlist(threads="any")`:** notices in any thread, and nothing more, through relayr's namespace allowlist ([relayr ADR-0029](../../relayr/adr/0029-an-allowlist-for-a-whole-rule-namespace.md)). Its `turns` stays `False`.
- **A rule from chat acts as itself.** Its actors, in reflexr and in artifactr, are checked as its grantr `RulePrincipal`. That principal holds the `rule` role in its own workspace with no grant ([grantr ADR-0029](../../grantr/adr/0029-a-stored-rule-acts-as-itself-in-its-own-workspace.md)), never the application's powers. A restricted thread stays out of its reach.
- **relayr's `relayr:rules-from-chat` is one of the application's code rules** (`CODE_RULES`), so its runs install, update and archive as the application, which holds those actions ([grantr ADR-0027](../../grantr/adr/0027-the-application-installs-the-rules-people-accept.md)).
- **Who may approve:**
  - With grantr, `may_change` asks grantr whether the person holds `reflexr:<change>` in the workspace.
  - Without access control, the template passes relayr's `anyone`.
- **The notes agent drafts with `draft_rule`.** `RuleDraft` is among artifactr's types, so a draft is a proposal people review in the thread.
- **The wiring order changes.** `draft_rule` needs reflexr's workspaces, and the reactor needs the bridge's actions, which act in artifactr. So `create_app` builds the bridge, then Automation with `Bridge.actions()`, then Collaboration with `Bridge.drafting(automation)`, and then calls `bridge.connect(...)`. The actions are delegates that act once `connect` has run, as `Bridge.watch` does. The delegates for rules from chat come from `STORED_RULES.actions`, each declaring its params model, so reflexr checks stored rules' params at startup, and each hands the params on as reflexr validated them.
- **relayr's `relayr:rules-from-chat` acts as the application,** so its "is live" notice reaches the thread a rule was proposed in, restricted or not. That is by design: whoever accepted it there could see the thread.
- **`make smoke-app`** gives a service principal's key a draft to propose, has the user accept it, and checks two things: the rule tells its thread of an alert, and a forged acceptance is refused at reflexr's publish gate. For determinism it proposes the raw artifact, skipping the agent, `check_draft` and the preview, which the template's tests cover.

## Options considered

| Option | For | Against |
|---|---|---|
| **`notify` alone (chosen)** | The smallest useful action, easy to bound | Rules from chat can only tell a thread |
| Every registered action | Rules from chat as capable as code rules | A person's draft could run the triage agent, with its cost, on any event |
| **Delegated actions, connected later (chosen)** | One order of construction; mirrors `watch` | The actions can't run before `connect` |
| The reactor built in the bridge's `connect` | No delegates | Automation's part loses its reactor until then, and its tests change shape |

## Consequences

- Easier: a person can ask the notes agent for a rule, read its preview, and put it live by accepting it.
- Harder: an action added to `STORED_RULES` reaches every rule from chat, and needs its grant in grantr's `rule` role. It gets its delegate from `STORED_RULES`, and needs a params model.
- Harder: without access control, every user may install rules, so anyone can put a `chat:` rule live directly through reflexr's REST and MCP, with no review. Use grantr wherever that matters.
