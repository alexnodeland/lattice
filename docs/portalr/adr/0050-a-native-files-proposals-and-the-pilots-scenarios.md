# ADR-0050: A native file's proposals: outdated, never rebased, and compared page by page; and the check-out pilot's scenarios

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#edits-json-patch-with-a-test) makes every revision of a native file a JSON Patch whose first operation tests the content digest it was made from. Accepting a proposal re-applies its patch to the head as it is then, so one made against a version since replaced fails as `PatchFailed`: "a stale proposal is outdated, never rebased. portalr shows it as outdated, and its author makes a new one." Two kinds of proposal reach a native file:

- **An agent's edit,** by the app's commands, under `WordDocument`'s `propose` policy. While a person has the file checked out, the agent's edit is refused as busy, and the agent is told who has it and to plan again once it is checked in; it never queues a proposal that would be stale on arrival ([native files ADR-0006](../../artifactr/files/adr/0006-the-agents-tools-behind-each-apps-switch.md)).
- **A person's stale check-in,** kept as a proposal against the head when the file moved on during the check-out: "the one proposal from a person, and the reviewer sees both versions' pages."

The RFC's exit criterion for phase 4 is `bdd` scenarios for a check-in, a stale check-in, an idempotent retry and a busy agent, and an editor origin that serves nothing that calls out. [ADR-0048](0048-native-files-in-the-app.md) and [ADR-0049](0049-checking-a-native-file-out-and-in.md) built the file's page, and its check-out and check-in.

## Decision

- **A native file's proposal is `NativeProposal`,** a `ProposalCard` with what its patch says of it, on the workspace's proposals and on the file's own page; any other proposal is the card it was.
  - **How it was made,** from the provenance its patch replaces: "The agent's edit, by WordCraft's commands", or "A check-in kept as a proposal: the file changed after it was checked out."
  - **Outdated, never rebased:** where the digest its patch tests isn't the head's, a badge says "Outdated", and Accept is disabled, kept in the tab order, and described by why: it was made against a version since replaced, so accepting it would fail; reject it, and ask the agent again, which plans again from the head, or, for a check-in, check the file out again from the head and make the change there. Reject stays. Whether it is outdated is said only once the head's revisions are read as far as the workspace's log has reached, so a reconnect's replay can't make it wrong. `ProposalCard` gains `blocked`, the reason a proposal can't be accepted, for this.
  - **A resolved proposal reads nothing more:** it says how it was made, and how it was resolved.
  - **Who has the file:** while someone has it checked out, the card warns, as a note of the page rather than an announcement, that accepting now makes their check-in, or the reader's own, a proposal in turn.
  - **Compared on demand:** "Compare with version N" reads the proposal's words and pages beside the head's, through the routes [native files ADR-0008](../../artifactr/files/adr/0008-what-portalr-reads-of-a-native-file.md) added, and shows the words' changes, and `ui`'s `PageCompare`: a row a page, the head's and the proposal's side by side, saying by a shape and a word whether it is unchanged, changed, new or gone, four pages at a time; the head's page count is its revision's, read with its version. Two renders of a page by one build are the same bytes, so "Changed" is said when their `data:` URLs differ. This is the RFC's "pages whose renders differ, side by side", which ADR-0048 deferred to here.
  - Accepting with changes isn't offered, as the RFC has it for native kinds.
- **The scenarios,** in `native-files.feature`, against the test application, where the scripted agent drafts a document, `draft the brief`, as the person who asked, and revises one, `revise <id>`, through `edit_native`:
  - **A check-in:** check it out, which opens the editor and downloads the file; check in the stand-in's file with a paragraph changed; it is version 2, and its outline says so.
  - **A stale check-in:** the agent proposes an edit; the person checks the file out, then accepts the agent's proposal, which the lease, being advisory, doesn't stop; their check-in is a proposal, which the proposals page shows with its pages beside version 2's.
  - **An idempotent retry:** Playwright lets the check-in reach the server and drops its answer; "Try again" sends the same file, which the server finds checked in already, and nothing new is made: the file stays at version 2. The check-in stays on the page though its lease is gone, for this.
  - **A busy agent:** asked while the person has the file checked out, the agent answers who has it, and that it plans again once it is checked in; asked again after the check-in, it proposes its edit.
  - **The editor serves nothing that calls out:** the test application's compose runs the editor as a service of its own, `editor`, under its own profile, on a port of its own, so another origin than the portal's: `editor_app` serving a stand-in in the shape of WordCraft's build (a page with an inline script allowed by its hash, its own script named by a hash, and WebAssembly it compiles), since the real build is 40 MB. `scripts/bdd` starts it first and names its address to the application, as `PORTALR_EDITOR_URL`, which `Site.editors` takes, at `localhost` while the application is at `127.0.0.1`, so another site, as a deployment's own host name is; the rest of the stack is started without recreating it, which would move its port. A shell that exports `PORTALR_EDITOR_URL` hosts an editor in any run of the test application, which only this script means to. The scenario hears every request and policy message on the browser's context from before the check-out opens it, waits for its WebAssembly to compile under its policy, finds every request it made on its own origin and no violation, and then has it try to reach the portal: refused, with a violation said. Nightly serves WordCraft's own build under the same policy (artifactr's `test_pilot_live.py`).

## Options considered

| Option | For | Against |
|---|---|---|
| **Outdated proposals refused before Accept (chosen)** | The reader isn't sent a failure they could have been told about | A read of the head's revisions for each native proposal shown |
| Accept offered, and the server's `PatchFailed` said | No read | A press that can only fail |
| Rebasing a stale proposal | No new request to the agent | RFC-0003 rules it out: WordCraft's commands act on positions, so a batch replayed on other content means something else |
| **Pages compared by their renders' bytes (chosen)** | No pixel comparison in the browser | A build that renders nondeterministically would say every page changed; WordCraft's renders were identical across processes (RFC-0003's evidence) |
| **A stand-in for the editor in the scenarios (chosen)** | Fast, small, in every pull request's run | It isn't WordCraft's build, which Nightly serves instead |
| WordCraft's build in the scenarios | The real build | 40 MB fetched on every run, and checksummed, for what the policy, not the build, decides |

## Consequences

- Easier: a reviewer sees what a native proposal would make of the file before accepting it, and isn't offered an accept that would fail; the RFC's exit scenarios run on every pull request.
- Harder: a proposals page with many native proposals reads each file's revisions once, and each comparison renders pages on the server, a render each.
- Revisit: the comparison's renders, cached by the RFC's key, once a deployment compares often.

## Action items

1. [x] `NativeProposal` and `PageCompare`, `ProposalCard`'s `blocked`, and their tests and screenshots.
2. [x] The test application's editor service, and the five scenarios.
