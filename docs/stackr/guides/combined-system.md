# The combined system

An application generated with both libraries and the `bridge` question is the combined system that [RFC-0002](../rfcs/0002-the-combined-system.md) designs. artifactr's chats and artifacts, and reflexr's events and rules, are joined by [relayr](../../relayr/index.md). This guide walks through what such an application does, using its example: incidents.

## Generate and run it

```sh
uvx copier copy gh:alexnodeland/lattice my-app   # libraries: both, bridge: yes
cd my-app
git init                                         # make install's git hooks need a repository
make install
make env                                         # .env from .env.example
make check                                       # lint, strict types, and tests at 100% coverage
make up                                          # beside stackr's stack, which `make up` in stackr starts
```

Before `make up`, fill in `LITELLM_API_KEY` and the Langfuse keys in `.env`, as the template guide's [Settings](template.md#settings) says. With grantr, make the first operator and a tenant before anyone signs in: `make operator EMAIL=...` and `make tenant NAME=acme OWNER=...`. The [template guide](template.md) lists every question and part.

## An incident, from alert to postmortem

The example's rules keep an incident in a thread people work in. Below, `<app>` is the application's package name, such as `my_app`.

1. **An alert opens the incident.** Monitoring publishes `<app>:alert.fired` into reflexr. `open-incident` creates an incident thread in artifactr, a `timeline` artifact in it, and a notice.
2. **People's messages join the timeline.** Each message in the thread reaches reflexr as `artifactr:message_posted`, and `timeline-entry` adds it to the timeline, keyed by its event.
3. **The resolution closes it.** `<app>:incident.resolved` fires `close-incident`, which posts a closing notice and proposes a `postmortem`, drawn from the timeline, for people to review.
4. **People review the postmortem.** Accepting it, editing it first, or rejecting it is scored, by relayr's evaluator, on the run that proposed it.

The rules act in artifactr as their own participants, within their allowlists: the timeline directly, everything else as a proposal or a notice. `make smoke-app` in stackr checks steps 1 to 3 on the stack ([smoke tests](smoke-tests.md)).

## Rules from chat

A person can ask the notes agent for a rule, such as "tell me here whenever checkout's alerts fire".

- **The agent drafts it** with `draft_rule`. That tool checks it against the application's event types and reflexr's limits on stored rules, previews how often it would have fired in the last week, and proposes it as a `rule` artifact in the thread.
- **A person puts it live by accepting it.** With grantr, that person must hold `reflexr:install_rule` in the workspace: a workspace's admins, a tenant's owners and admins, or a custom role with it. An editor may accept the proposal, but no rule goes live.
- **It runs as itself.** A rule from chat is named in the `chat` namespace, and runs only `notify`, a notice in the thread it names. With grantr it acts as its own principal, which can't post into a restricted thread.
- **Changes come back.** Accepting a change to the artifact updates the rule, and archiving the artifact archives it. A rule changed in reflexr directly, by someone who may change rules there, is proposed back to its artifact in the same thread.

!!! warning "Without access control, everyone may install rules"

    With `access=none`, every user of a tenant may install `chat:` rules, through the drafts they accept, or directly through reflexr's REST and MCP. Use grantr wherever that matters.

## Measuring it

`make evals` runs the starter experiments offline, with a scripted model. With `bridge`, `incident-scenarios` plays incidents through the application itself, and reports, for each:

- how the postmortem was taken: accepted, edited or rejected;
- the postmortem's rewrite rate: how much of what the rule proposed people rewrote;
- the time from the alert to its resolution.

`make evals-langfuse` runs them in Langfuse, with the gateway's model. relayr's [evaluation guide](../../relayr/guides/evaluation.md) describes the outcomes and measures, and how to read a chain's cost in Langfuse.

## Where each part is decided

| Part | Decided in |
|---|---|
| The bridge in the template | [ADR-0021](../adr/0021-the-bridge-in-the-template.md) |
| Rules from chat in the template | [ADR-0024](../adr/0024-rules-from-chat-in-the-template.md) |
| The incident experiment, and its postmortem | [ADR-0030](../adr/0030-the-incident-experiment-and-its-postmortem.md) |
| relayr's own decisions | [relayr's decision records](../../relayr/adr/README.md) |
