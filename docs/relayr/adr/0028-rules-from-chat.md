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
  - `check_draft` runs `Rule.check` and reflexr's `check_stored` against the events and `StoredRules` the application gives it.
  - The installer reads the draft from artifactr again.
  - reflexr checks it all once more at install.
- **The chat agent drafts through `RuleDrafting`'s `draft_rule` tool.**
  - It checks the draft and hands any problems back to the model.
  - It previews the draft: `preview` replays reflexr's log for the window, a week by default, through core's pure `evaluate`, running nothing.
  - It proposes the draft as a new `rule` artifact, or as an edit of one, with the preview in the rationale.
- **relayr's code rules make each change.** `relayr:install-rule` fires on an accepted proposal, and `relayr:archive-rule` on an archived `rule` artifact. Their actions are `Installer`'s.
- **Neither trusts the bridged event.** Each re-reads artifactr as its rule's own participant. It acts only if the proposal is accepted, its artifact is a `rule`, and the artifact is still at the version the acceptance made, or the one that archived it. A later change acts for itself. A forged event finds nothing to act on.
- **The approver is the actor of artifactr's revision at that version.** artifactr records who applied each revision, with the proposal it applied, so no log scan is needed.
- **The approver must be a person who may make the change.** It must be a `UserActor`, and `may_change(tenant, workspace, person, change)` checks it against reflexr's action for the change: `install_rule`, `update_rule` or `archive_rule`. Without access control, any person may. With grantr, the template asks grantr ([grantr ADR-0027](../../grantr/adr/0027-the-application-installs-the-rules-people-accept.md)).
- **An artifact installs one rule, under one name.**
  - The rule installed from an artifact is the stored rule whose provenance names it.
  - A later accepted change updates that rule, with the version read as `expected_version`.
  - A change of name is refused with a notice: archive the rule, and draft the new one apart.
  - A name another artifact installed is refused by reflexr, and reported.
- **Provenance** is `{source, artifact, artifact_version, proposal, approved_by}`. reflexr's audit shows the application as each change's actor, so provenance names the person.
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
- Harder: the template has to pass `StoredRules`, the events, `may_change` and relayr's rules, and list relayr's rules among its code rules so their runs act as the application. That is phase 5's template change.
- Deferred: proposing changes made in reflexr directly back to the artifact (drift, [ADR-0005](0005-where-a-rules-source-of-truth-lives.md)), in a pull request of its own.
