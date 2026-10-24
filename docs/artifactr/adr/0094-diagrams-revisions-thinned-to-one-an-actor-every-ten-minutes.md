# ADR-0094: Diagrams' revisions thinned to one an actor every ten minutes

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland
**Implements:** the retention rule of [ADR-0091](0091-diagrams-tombstones-swept-and-their-revisions-thinned.md), as the owner ratified it on 2026-10-23, and [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 4 thinning
**Narrows:** [ADR-0004](0004-optimistic-concurrency-and-revisions.md): revisions are no longer kept forever

ADR-0093 is not missing: it is portalr's presence's, on its own pull request.

## Context

- **Every save of a canvas is a revision**, and every revision holds the whole scene. Phase 0 measured about 29 MB a person-hour at a 30 KB scene under the five-second cadence ([ADR-0088](0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md)).
- **The rule is ratified** (ADR-0091): after 24 hours, thin to one revision an actor every ten minutes; keep the revisions that pending proposals are based on; remove tombstones after 24 hours by the sweep.
- **Storage had no way to forget a revision.** Revisions were append-only, as the log is.

## Decision

- **`Storage.drop_revisions(scope, artifact_id, versions)`** forgets some of an artifact's earlier revisions and answers with how many. It is a new method of the `Storage` port: a storage outside artifactr implements it to upgrade, a breaking change.
  - It never forgets the current version, whatever it is asked: the head stays what the artifact is.
  - A version it doesn't hold is passed over.
  - The log's events, which say what each revision changed, are never touched.
  - The in-memory and SQL storages both implement it. SQL deletes within the tenant's scope, through its row-level security as every write does.
  - SQL deletes at most 500 versions a statement, in one transaction, as a database takes a bounded number of parameters; `thin_revisions` hands it 500 at a time too.
  - The storage contract tests it on every backend, with the same artifact in a second tenant, and in a second workspace of the same tenant, untouched.
- **`thin_revisions(storage, scope, *, now, integrations=None)`** in `artifactr.excalidraw` thins a workspace's diagrams, archived ones too.
  - It works on the storage as the application's own maintenance, with no actor: it changes no diagram, only how much of its history is kept.
  - It reads each diagram's revisions first, then the pending proposals. A proposal made after a diagram's revisions were read is based on a revision this read didn't hold, the head then, which is never forgotten; read the other way round, such a proposal's base could be thinned.
  - Where `integrations` says diagrams are off in the workspace, nothing is thinned, as nothing is swept.
- **What is kept**, in `thinned`, a function of a diagram's revisions:
  - the current version, which is what the diagram is;
  - **the first**, the diagram as it was made. The rule is silent on it; the owner approved keeping it (2026-10-24), a deviation from the rule as written, so a diagram's history always starts where it began;
  - **each revision an accepted proposal made** (one with a `proposal_id`). The owner approved this too (2026-10-24), beyond the rule as written: what an agent proposed and a person accepted stays, for evaluation and for review, whatever its age;
  - the revisions pending proposals (`EditArtifact` ones) are based on, so a proposal is still compared and applied as it was made;
  - every revision 24 hours old or less: one exactly 24 hours old is kept (`THIN_AFTER`);
  - of the older ones, the latest of each actor (by `participant`) in each ten-minute span (`THIN_EVERY`; fixed spans, from the epoch).
- **An undated revision**, saved before artifactr stamped revisions' times, counts as old, as the sweep counts it. An actor's undated revisions are one span, so the latest of them is kept.
- **Thinning makes the sweep date a tombstone later, never earlier.** The sweep dates a tombstone by the first revision holding it. If an earlier one is gone, it dates by a later one, so a tombstone is kept a little longer, never removed early.
- **A revision's comparison in the UI** is with the revision kept before it: what changed since the last one kept.

## Consequences

- A diagram's history grows with its edits for a day, then at most six revisions an hour per actor, besides the revisions accepted proposals made, which are never thinned. A diagram an agent drives, where every revision is an accepted proposal, grows without bound, one revision a proposal; each needs a person to accept it, so it grows slowly, and that is accepted.
- **A version number can now be missing from an artifact's revisions**, and some readers assumed it never was. Each now reads a gap:
  - the feedback mirror (`artifactr.scores`) scores feedback on a forgotten version on neither a trace nor a session: whose it was is gone;
  - evaluation's context (`artifactr.evals`) gives no revision for feedback on a forgotten version, and an artifact a thread followed at a forgotten version as the latest kept before it;
  - relayr's proposal outcomes compare an accepted proposal's revision with the kept revision before it, not with the version one less. Where the one just before was thinned, a proposal accepted unchanged can read as `edited`; that imprecision is accepted;
  - native files' reads at a forgotten version answer 404, as at a version that never was;
  - portalr's revision list compares each revision with the one kept before it: what changed since the previous kept version. A proposal's card compares the proposal with the head, which is never forgotten.
- **Thinning reads every body.** Every hour it reads every revision of every diagram, archived ones included, and `storage.revisions` loads each revision whole, so thinning a diagram holds its whole history in memory once, for a moment; thinning keeps only each revision's version, actor, time and proposal after reading. A listing of revisions without their bodies is the follow-up that removes the cost.
- Applications run thinning on a schedule beside the sweep (stackr ADR-0052).

## Alternatives considered

- **Thinning through a workspace handle and a new action:** rejected. It would need an action in grantr's catalog and a grant for the application's actor, for maintenance that changes nothing a person reads as the artifact.
- **Dropping the first revision too:** rejected by the owner. A history that starts mid-way reads as if the diagram had no beginning.
- **Thinning an accepted proposal's revision as any other:** rejected by the owner. Proposal outcomes and reviews read it, and it is one revision a proposal.
- **Thinning the log's events too:** rejected. The log is the record every reader and every bridge follows, and its events are small beside a revision's whole scene.
