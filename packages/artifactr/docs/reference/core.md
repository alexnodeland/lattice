# artifactr.core

::: artifactr.core
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Artifacts

Artifact types, stored versions and the type registry. See [Defining artifact types](../guides/artifact-types.md).

::: artifactr.core.Artifact

::: artifactr.core.MarkdownArtifact

::: artifactr.core.Versioned

::: artifactr.core.WritePolicy

::: artifactr.core.create_artifact

::: artifactr.core.artifact_types

::: artifactr.core.get_artifact_type

::: artifactr.core.load_artifact

::: artifactr.core.load_versioned

## Actors

Who did something. See [Opening a workspace](../guides/workspaces.md#opening-a-workspace).

::: artifactr.core.Actor

::: artifactr.core.UserActor

::: artifactr.core.AgentActor

::: artifactr.core.ExternalAgentActor

::: artifactr.core.SystemActor

::: artifactr.core.is_agent

::: artifactr.core.same_participant

## Commands

Intents to change a workspace. See [Commands and outcomes](../guides/workspaces.md#commands-and-outcomes).

::: artifactr.core.Command

::: artifactr.core.CreateArtifact

::: artifactr.core.EditArtifact

::: artifactr.core.ArchiveArtifact

::: artifactr.core.ProposeChange

::: artifactr.core.ProposedChange

::: artifactr.core.RespondToProposal

::: artifactr.core.CreateThread

::: artifactr.core.PostMessage

::: artifactr.core.SetFocus

::: artifactr.core.SetThreadMode

::: artifactr.core.ThreadMode

::: artifactr.core.AnswerDeferred

## Outcomes

What a command did.

::: artifactr.core.Outcome

::: artifactr.core.Applied

::: artifactr.core.Proposed

::: artifactr.core.Resolved

::: artifactr.core.Recorded

## Rejections

The ways a command can fail. See [Rejections](../guides/workspaces.md#rejections).

::: artifactr.core.Rejection

::: artifactr.core.VersionConflict

::: artifactr.core.ValidationFailed

::: artifactr.core.PatchFailed

::: artifactr.core.NotFound

::: artifactr.core.Forbidden

::: artifactr.core.InvalidState

::: artifactr.core.UnsupportedProtocol

## Patches

The two ways artifact data changes. See [How changes are expressed](../guides/artifact-types.md#how-changes-are-expressed).

::: artifactr.core.Patch

::: artifactr.core.JsonPatch

::: artifactr.core.TextEdits

::: artifactr.core.TextEdit

::: artifactr.core.apply_patch

::: artifactr.core.diff

::: artifactr.core.describe_patch

## Entities

Threads, proposals, revisions and runs, as stored.

::: artifactr.core.Thread

::: artifactr.core.Proposal

::: artifactr.core.Revision

::: artifactr.core.Run

::: artifactr.core.RunStatus

::: artifactr.core.DeferredAnswer

## Events

Facts on a workspace's log, and the envelope each travels in. See [The log](../guides/workspaces.md#the-log).

::: artifactr.core.Envelope

::: artifactr.core.Event

::: artifactr.core.KnownEvent

::: artifactr.core.UnknownEvent

::: artifactr.core.ThreadCreated

::: artifactr.core.ThreadModeChanged

::: artifactr.core.FocusChanged

::: artifactr.core.MessagePosted

::: artifactr.core.ArtifactCreated

::: artifactr.core.ArtifactChanged

::: artifactr.core.ArtifactArchived

::: artifactr.core.ProposalCreated

::: artifactr.core.ProposalResolved

::: artifactr.core.RunEvent

::: artifactr.core.RunStarted

::: artifactr.core.ToolCalled

::: artifactr.core.ToolReturned

::: artifactr.core.RunPaused

::: artifactr.core.DeferredRequest

::: artifactr.core.DeferredAnswered

::: artifactr.core.RunEnded

::: artifactr.core.RunUsage

::: artifactr.core.AppEvent

::: artifactr.core.scope_of

::: artifactr.core.delivered_to

## Rules

The host contract: what to load, and how a command or a fact is decided ([ADR-0018](../adr/0018-core-host-contract.md)). `Workspace.commit` and `Workspace.record` use these; call them directly only when you write a host of your own.

::: artifactr.core.needs

::: artifactr.core.commit

::: artifactr.core.record

::: artifactr.core.Fact

::: artifactr.core.NotLoaded

::: artifactr.core.State

::: artifactr.core.Needs

::: artifactr.core.CommitResult

## Change notes

What others did, told to one viewer. See [Change notes](../guides/workspaces.md#change-notes).

::: artifactr.core.change_notes

::: artifactr.core.render_notes

::: artifactr.core.Note

::: artifactr.core.ChangeNote

::: artifactr.core.ProposalNote

## Live events

A run's token-level output. See [Live output](../guides/live-output.md).

::: artifactr.core.LiveFrame

::: artifactr.core.LiveEvent

::: artifactr.core.PartStarted

::: artifactr.core.TextDelta

::: artifactr.core.ThinkingDelta

::: artifactr.core.ToolArgsDelta

::: artifactr.core.PartEnded

::: artifactr.core.Draft

::: artifactr.core.AppLive

## Protocol frames

The thread protocol's frames and its resume rule. See the [thread protocol](../protocol.md).

::: artifactr.core.PROTOCOL

::: artifactr.core.Hello

::: artifactr.core.Welcome

::: artifactr.core.ActiveRun

::: artifactr.core.EventFrame

::: artifactr.core.ReplayComplete

::: artifactr.core.CommandFrame

::: artifactr.core.FrameCommand

::: artifactr.core.StopRun

::: artifactr.core.WatchRun

::: artifactr.core.CommandResult

::: artifactr.core.ErrorFrame

::: artifactr.core.ClientFrame

::: artifactr.core.ServerFrame

::: artifactr.core.resume

::: artifactr.core.ResumePlan

## Identifiers

Identifiers are plain strings. These aliases say what a string identifies, and the factories generate ids with a short type prefix.

::: artifactr.core.TenantId

::: artifactr.core.WorkspaceId

::: artifactr.core.ArtifactId

::: artifactr.core.ThreadId

::: artifactr.core.RunId

::: artifactr.core.ProposalId

::: artifactr.core.MessageId

::: artifactr.core.new_id

::: artifactr.core.new_artifact_id

::: artifactr.core.new_thread_id

::: artifactr.core.new_run_id

::: artifactr.core.new_proposal_id

::: artifactr.core.new_message_id
