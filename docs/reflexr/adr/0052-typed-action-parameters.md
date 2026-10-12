# ADR-0052: Typed action parameters

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0008](0008-actions-agents-graphs-and-functions.md), the action port. Decided on [RFC-0003](../rfcs/0003-managing-rules-at-runtime.md), against its simplicity review's recommendation.

## Context

A rule names its action, and every rule that names an action runs it the same way. "Whenever a deploy to production fails, tell me here" needs the rule to say where "here" is: its chain begins at a deploy, not in a thread. A chat can't register an action for each thread, and a stored rule can't carry code.

## Decision

- **A rule passes values to its action.** `ActionRef` gains `params`, a JSON object, empty by default, which `run(action, **params)` fills. Params aren't part of `Rule.definition()`, so changing them never resets a rule.
- **An action may declare a params model, and the port doesn't change.** `Action[D]` is still an async callable over `Reaction[D]`, and a plain function without params is still an action. An action declares its model through a `params` attribute:
  - `with_params(fn, Model)` adapts a function of `(Reaction[D], P)`, and pyright checks that `fn`'s second parameter takes a `Model`
  - `AgentAction(..., params=Model)` and `GraphAction(..., params=Model)` gain the field
  - the reactor reads the attribute where there is one, through a runtime-checkable protocol
- **`Reaction[D]` gains `params`,** the validated model or `None`, and `params_as(Model)`, which returns it typed. Functions get it as their second argument; agents' tools and prompts, and graphs' steps, call `params_as`.
- **Checked before a rule runs.** The reactor validates each code rule's params against its action's model when it is built, and `InvalidRule` lists every problem, as for a missing action. A stored rule's params are checked when it is installed or updated ([ADR-0053](0053-stored-rules-one-fixed-configuration.md)).
- **Validated again at each attempt,** into `Reaction.params`. A rule whose params no longer validate after a deploy fails its attempt permanently with the reason `invalid_params`, and one whose action a deploy removed with `unknown_action`.

## Options considered

| Option | For | Against |
|---|---|---|
| None: one registered action per behaviour | Nothing to build | A chat rule can't register an action per thread |
| Free JSON, passed to the action | Little to build | A draft a person accepted fails only when it fires |
| **Typed through the action port, checked at install and at startup (chosen)** | Bad params fail before a rule runs, for stored and code rules alike | A `params` field and a function adapter, and an agent or graph names its model twice |

## Trade-off analysis

`Reaction[D]` and `Action[D]` keep their one type parameter, so no existing action, capability or `RunContext` changes. The price is that an agent or graph names its model twice, in `params=` and in `params_as`, and a mismatch is a `TypeError` when it runs, not a type error. Only functions, through `with_params`, are checked end to end.

The fully typed alternative is `Reaction[D, P]`, with a default for `P`. A type parameter default needs PEP 696, whose syntax needs Python 3.13, and reflexr supports 3.12, so `Reaction` would move to `typing_extensions` and every action type would gain a parameter: `Action`, `AgentAction`, `GraphAction` and `RunContext`.

## Consequences

- Easier: one action serves many rules that differ in a value, such as a thread or a service.
- Easier: a rule's params are checked against the same model at startup, at install, and before each attempt.
- Harder: an agent or graph names its params model twice, and a stored rule's action names it a third time, in `StoredRules.actions`, since installs are checked where no reactor is. The reactor's startup check keeps them from disagreeing.

## Action items

1. [x] `ActionRef.params`, `with_params`, `params=` on agents and graphs, and `Reaction.params` (alexnodeland/reflexr#86).
