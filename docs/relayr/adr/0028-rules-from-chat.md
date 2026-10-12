# ADR-0028: Rules from chat

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds phase 5 of [RFC-0001](../rfcs/0001-v0.1-implementation-plan.md), as [stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md#rules-from-chat) designs it, on reflexr's stored rules ([reflexr RFC-0003](../../reflexr/rfcs/0003-managing-rules-at-runtime.md)).

## Context

A person asks in a thread for something to happen whenever something else does. The chat agent drafts a reflexr rule as a `rule` artifact, a person accepts it, and relayr installs it in reflexr. The artifact is the reviewed record, and reflexr's store holds the running definition ([ADR-0005](0005-where-a-rules-source-of-truth-lives.md)).

- **artifactr validates an artifact with a plain `model_validate`.** It passes no context, so an artifact type can't see the application's event types or its `StoredRules`.
- **Anyone allowed to publish could forge a bridged `artifactr:proposal_resolved`,** though reflexr now reserves the namespace to relayr's source ([reflexr ADR-0057](../../reflexr/adr/0057-reserved-publishers.md)).

## Decision

- **`RuleDraft`, the `rule` artifact type, checks the rule's shape alone.** Its data is `{rule: Rule}`, and its write policy is `propose`. Three checks cover what the type can't see:
  - `check_draft` runs `Rule.check` and reflexr's `check_stored` against the events the application gives it and the stored rules' configuration of its reflexr workspaces.
  - The installer reads the draft from artifactr again.
  - reflexr checks it all once more at install.
- **The chat agent drafts through `RuleDrafting`'s `draft_rule` tool.**
  - It checks the draft and hands any problems back to the model, a change of name included.
  - It previews the draft: `preview` replays reflexr's log for the window, a week by default, through core's pure `evaluate`, running nothing.
  - The preview reads the log as the person the turn acts for, so it counts only what they may read. A turn that acts for no person can't draft.
  - It proposes the draft as a new `rule` artifact, or as an edit of one, with the preview in the rationale.
- **One code rule makes every change.** `relayr:rules-from-chat` fires on an accepted proposal and on an archived `rule` artifact, with `Installer`'s action. It is scoped by the artifact, with reflexr's default ordering, so one artifact's acceptances and archive run one at a time, in the order they happened: an archive can't come between an install's reading of artifactr and its install.
- **It never trusts the bridged event.** It re-reads artifactr as its rule's own participant. It acts only if the proposal is accepted, its artifact is a `rule`, and the artifact is still at the version the acceptance made, or at the one that archived it. A later change acts for itself, and a forged event finds nothing to act on.
- **A replayed acceptance changes nothing.** reflexr's `rule_installed` facts carry provenance, so an acceptance already installed is passed over, even when an operator has since archived its rule in reflexr.
- **The approver is the actor of artifactr's revision at that version.** artifactr records who applied each revision, with the proposal it applied, so no log scan is needed.
- **The approver must be a person who may make the change.** It must be a `UserActor`; an agent's acceptance puts nothing live. `may_change(tenant, workspace, person, change)` checks the person against reflexr's action for the change: `install_rule`, `update_rule` or `archive_rule`. It is required. An application without access control passes `anyone`, so the open choice is visible. With grantr, the template asks grantr ([grantr ADR-0027](../../grantr/adr/0027-the-application-installs-the-rules-people-accept.md)).
- **An artifact installs one rule, under one name.**
  - The rule installed from an artifact is the active stored rule whose provenance names it.
  - A later accepted change updates that rule, passing the version just read as `expected_version`.
  - A change of name is refused with a notice: archive the rule, and draft the new one apart.
  - A name another artifact installed is refused by reflexr, and reported.
- **Only accepted proposals install.** A person who writes to a `rule` artifact directly installs nothing: the write policy asks agents to propose, and the rule fires on acceptances.
- **Provenance** is `{source, artifact, artifact_version, proposal, approved_by}`. reflexr's audit shows the application as each change's actor, so provenance names the person. Provenance is a claim, as reflexr says: anyone allowed to install rules directly can write any `provenance.artifact`, and relayr then treats that rule as the artifact's.
- **Notices** in the draft's thread say that a rule is live, archived or refused, with reflexr's problems listed. A draft outside a thread is changed silently.

## Options considered

| Option | For | Against |
|---|---|---|
| **Structural type, checks in the tool (chosen)** | No change to artifactr; every check has the registry it needs | A draft written without the tool is checked only at install, where a notice reports the problems |
| A type made by a factory that closes over the registry | artifactr checks the draft | Fights artifactr's global type registry when made twice, as tests do |
| **The approver from the revision (chosen)** | artifactr's own record, read by artifact; no scan | The artifact's revisions are read whole |
| The approver from the log's `proposal_resolved` envelope | The envelope itself | A scan of the log by proposal id |
| **One rule per artifact, renames refused (chosen)** | No rule left running under an old name | Renaming takes an archive and a new draft |
| The name derived from the artifact's id | No clashes and no renames | Names people can't read, from ids clients may choose |

## Consequences

- Easier: a person can ask for a rule in chat, read what it would have done, and put it live by accepting it.
- Harder: the template has to pass `StoredRules`, the events, `may_change` and relayr's rule, and list that rule among its code rules so its runs act as the application. That is phase 5's template change.
- Harder: an install reads reflexr's `rule_installed` facts, and every active stored rule's provenance, one rule at a time; reflexr keeps at most 50 per workspace.
- Deferred: proposing changes made in reflexr directly back to the artifact (drift, [ADR-0005](0005-where-a-rules-source-of-truth-lives.md)), in a pull request of its own.
