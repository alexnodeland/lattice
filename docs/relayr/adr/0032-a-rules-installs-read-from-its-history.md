# ADR-0032: A rule's installs, read from its history

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0030](0030-drift-proposed-back-to-a-rules-artifact.md): how relayr reads its own installs

## Context

[ADR-0030](0030-drift-proposed-back-to-a-rules-artifact.md) has relayr know a rule from chat by the installs `relayr:rules-from-chat` made. reflexr could only read facts by type, so relayr read the latest 1,000 `reflexr:rule_installed` facts on every install and every drift run, and filtered them itself. An install older than those was invisible: its rule drifted unproposed, and a replay of its acceptance installed it again. reflexr now reads one stored rule's history by its name ([reflexr ADR-0063](../../reflexr/adr/0063-a-stored-rules-history.md)), but not facts by their provenance, which is relayr's and opaque to reflexr.

## Decision

- **relayr reads a rule's installs from its history,** `Workspace.rule_history`, and keeps those `relayr:rules-from-chat` made, as before. Nothing else reads the log's install facts, so the 1,000-fact window, `INSTALLS_READ`, is gone.
- **Each question starts from a rule's name, which relayr finds in artifactr:**
  - **Drift:** the changed rule's name is on its fact. Its history says where relayr last installed it from.
  - **A replayed acceptance:** the accepted revision holds the draft, and so the rule's name. Its history says whether an install names the proposal already.
  - **The rule an artifact installed:** each of the artifact's revisions holds a draft, and so a name. The history of each name the drafts held says whether relayr installed it from this artifact. An installed rule can't be renamed, so this is almost always one name; a draft renamed before anything installed it adds another.

## Options considered

| Option | For | Against |
|---|---|---|
| **Names from artifactr, then each rule's history (chosen)** | Reads only the rules concerned, however old their installs | A read per name a draft held |
| A filter by provenance in reflexr | One read | Provenance is the installer's, unindexed JSON reflexr doesn't read |
| relayr's own map of artifacts to rules, in its ledger | One read | A second write, outside reflexr's transaction, which can disagree with the log |

## Consequences

- Easier: an install however far back is still relayr's. Its rule's drift is proposed, and a replay of its acceptance changes nothing.
- Harder: relayr needs reflexr with `rule_history`, as the packages in lattice have.
