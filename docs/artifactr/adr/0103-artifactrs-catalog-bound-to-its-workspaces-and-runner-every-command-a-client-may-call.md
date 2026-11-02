# ADR-0103: artifactr's catalog bound to its workspaces and runner: every command a client may call

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Tracking item "artifactr, grantr, reflexr, relayr, portalr: their catalogs, providers, ..." for artifactr (#916); beside [ADR-0099](0099-artifactrs-tools-as-capabilities-called-through-the-enforcer-whose-policy-asks-approval.md) and [ADR-0100](0100-artifactrs-commands-every-action-a-command-or-listed-with-its-reason.md)

## Context

ADR-0100 declares artifactr's 24 commands in a static catalog, but nothing serves most of them. ADR-0099's `ArtifactrProvider` serves six: the agent's artifact tools, for callers outside artifactr's threads. It commits in no thread and never goes through the runner, so a message posted through it would start no turn. portr's MCP server (#917) reaches each package's commands only through lattice-core's registry (lattice ADR-0043), so artifactr needs a provider for the rest of its catalog.

Making them callable showed three commands whose arguments couldn't carry out the core command they name:

- **`artifactr.edit_artifact`** had no base version, which `EditArtifact` needs to refuse an edit made against a version that has since changed.
- **`artifactr.give_feedback`** took a rating and a comment, but `GiveFeedback` takes a registered feedback type, a target of one of four kinds, and the type's fields.
- **`artifactr.set_thread_mode`'s `mode`** was any string, though a thread has two modes.

No surface served them yet, so no client has called them.

## Decision

- **`artifactr.capabilities.ArtifactrCatalogProvider(workspaces, runner, *, types, actor=actor_for)`** is lattice-core's `Provider` and `Commands` for artifactr's catalog. It offers each exposed command except native files' two, 20 in all.
- **It is a surface, so it carries each write out through `Runner.execute`,** under a new command id, as artifactr's REST and MCP surfaces do (ADR-0048):
  - A message starts or steers its thread's turn; a message with no thread starts one first.
  - `artifactr.stop_run` stops a run going in this process.
  - A refusal raises `CommandRejected`, a `Rejection` whose payload is the workspace's.
  - Reads use the workspace's methods and answer text: JSON lines for lists, the agent's own text for artifacts, and a JSON object of a thread and its events for `artifactr.read_thread`.
- **It opens the call's workspace as `actor_for`'s actor,** as ADR-0099's provider does, so the workspace's `authorize`, gate and checks hear each call again after the enforcer's steps.
- **`artifactr.list_workspaces` is tenant-wide** (lattice ADR-0044): it lists the tenant's workspaces the actor may open, whatever workspace the call names. Any other command called with no workspace is refused with `ValueError`.
- **Not offered, and refused with `ValueError` if called:**
  - the commands not exposed, `artifactr.answer_deferred` and `artifactr.set_focus`, which are portalr's alone;
  - native files' `artifactr.list_files` and `artifactr.read_file`, which need the files extra's `NativeFiles` and come with a provider of that extra's own.
- **`artifactr.create_artifact`** names the application's kinds and describes each one's JSON Schema, as ADR-0099's provider does. The catalog's own capability is unchanged.
- **The catalog's arguments are public:** `artifactr.commands.arguments` holds each command's model, and `artifactr.commands.ARGUMENTS` maps each command's name to its model. The input schemas are these models', and the provider validates a call with them. Three of them change before anything serves them, which is not a breaking change under RFC-0014's P4:
  - `EditArguments` gains `base_version`;
  - `FeedbackArguments` takes `feedback_type`, `target` and `value`, whose targets mirror core's, as a test holds them;
  - `ModeArguments.mode` is `edit` or `suggest`, core's modes, as a test holds them.
- **ADR-0099's `ArtifactrProvider` stays** for the agents' toolset, unchanged. The two share six names, so a registry holds one of them: portr's the catalog provider, an agent's bridge the six tools.

## Options considered

### Option A: A provider of the catalog's own, through the runner (chosen)

**Pros:** a client's message starts a turn, a retry is a new command id, and stopping a run works, all as on every other surface. The agents' six tools keep their behaviour.
**Cons:** two providers share six names, so an application picks one per registry.

### Option B: Widen ADR-0099's provider to the whole catalog

**Cons:** it commits in no thread and never through the runner, so a message would start no turn. Making it go through the runner would change what the agents' six tools do, and every agent bridged to it would see 20 tools, among them listing workspaces and stopping runs.

### Option C: Version the three commands as `_v2`

**Cons:** nothing called the old shapes, which couldn't be carried out, so a `_v2` would keep three dead commands in every client's tool list for a release.

## Consequences

- Easier: portr's MCP server offers artifactr's catalog through the registry, and lattice's enforcement suite can hold the catalog provider to the enforcer as it holds ADR-0099's.
- Harder: an application that bridges agents and serves portr composes two registries, or leaves the six tools out of one.
- To revisit: native files' provider, in the files extra, for `artifactr.list_files` and `artifactr.read_file`.
