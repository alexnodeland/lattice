# Acting in artifactr from rules

This guide lets a rule's run act back in artifactr: propose changes, make keyed edits and post notices in the thread its chain came from. It builds on [bridging artifactr into reflexr](inbound.md), which runs the followers; the [architecture](../architecture.md) says how both work.

## Wire it in

`Outbound` needs the artifactr workspaces, the ledger the followers use, and each rule's allowlist. Give it to the reactor as its dependency:

```python
from relayr.outbound import Allowlist, Outbound

outbound = Outbound(
    collaboration,
    ledger,
    allowlists={"ops:timeline": Allowlist(direct=frozenset({"timeline"}))},
    runner=runner,  # artifactr's Runner, for rules allowed to start turns
)
reactor = Reactor(automation, actions=actions, deps=outbound)
```

The ledger must be the followers' own: they read what `Outbound` records there to continue each run's causal chain.

## From a function action

`outbound.acting(reaction)` is what the attempt may do in artifactr, as the rule's own participant:

```python
async def log_deploy(reaction: Reaction[Outbound]) -> None:
    acting = reaction.deps.acting(reaction)
    await acting.edit(TIMELINE, f"/entries/{reaction.run_id}", "deployed", summary="deploy")
    await acting.notice("Added the deploy to the timeline.")
```

| Method | Does | By default |
|---|---|---|
| `create(artifact)` | Creates an artifact | As a proposal |
| `edit(artifact_id, path, value)` | Sets one value at a JSON Pointer path; skipped when it is in place | As a proposal |
| `notice(content)` | Posts a notice, which starts no turn | Allowed |
| `create_thread(title)` | Creates a thread the run may then act in | Refused |
| `send(content)` | Posts a message that starts the assistant's next turn | Refused |
| `read(artifact_id)` | Reads an artifact's current version | Allowed |

Each write goes to the thread named, or to the first thread of the events that made the rule fire.

## From an agent

Add `ArtifactrCapability` beside reflexr's `EventContext`:

```python
from relayr.outbound import ArtifactrCapability

agent = Agent(model, deps_type=Reaction[Outbound], capabilities=[
    EventContext(),
    ArtifactrCapability(outbound),
])
actions = {"runbook": AgentAction(agent)}
```

Its tools are `read_artifact`, `create_artifact`, `edit_artifact`, `post_notice`, `create_thread` and `send_message`. What the allowlist refuses comes back to the model as a retry, so it can post a notice instead.

## Allowlists

| Field | Grants | Default |
|---|---|---|
| `direct` | Creating and editing these artifact kinds without proposing | None |
| `threads` | `any` thread, rather than the chain's | `chain` |
| `create_threads` | Creating threads | No |
| `turns` | Sending messages that start a turn; needs `Outbound(runner=...)` | No |

artifactr's write policy and the thread's mode still apply: a direct edit to a kind whose policy is `propose` is still a proposal.

## Retries and failures

Write as if every attempt were the first. Each write's ids are derived from the run, so a retried attempt that makes the same writes in the same order makes nothing twice. Make them in the same order on every attempt.

- **A version conflict** re-reads the artifact and edits again, up to three times, then fails the attempt to be retried.
- **Anything else artifactr refuses** fails the run for good, with the refusal's code as its reason, such as `forbidden` or `not_found`.
- **What the allowlist refuses** is `NotAllowed`, which fails the run for good too, with the reason `not_allowed`.

## Loops

Every write a run makes continues the run's causal chain when the followers bridge it back, as deep as the run's own events, so rules that answer each other stop at reflexr's depth limit (`Workspaces(max_depth=...)`, 8 by default). A person who accepts or rejects a rule's proposal joins its chain without going deeper. Rules should still ignore writes they don't need to see, by their author, as `on(MessagePosted).where(F.author.kind.eq("user"))` ignores every rule's and agent's.

## Access

With access closed by an `authorize` hook, such as grantr's, each rule's actor needs the artifactr actions [ADR-0022](../adr/0022-what-a-rules-actor-needs-in-artifactr.md) lists: `open`, `read_artifacts`, `propose_change` and `post_message` always, and more for what its allowlist grants.
