---
name: rfc-status
description: Move a lattice RFC to a new status (Draft, Discussion, Accepted, Rejected, Withdrawn, Implemented, Superseded), keeping its README row and its Tracking section in step. Use when an RFC is accepted, implemented, rejected or superseded, when ticking its Tracking items, or when asked where an RFC stands.
---

# An RFC's status

An RFC's statuses, from `docs/rfcs/template.md`: **Draft → Discussion → Accepted → Implemented**, or **Rejected**, **Withdrawn**, or **Superseded by RFC-NNNN**. Only the user decides a proposal's fate: move it to Accepted, Rejected or Withdrawn when they say so, not on your own reading.

1. **Find it:** `docs/rfcs/NNNN-*.md` for lattice's, `docs/<package>/rfcs/NNNN-*.md` for a package's.
2. **Change its `**Status:**` line.** An amendment stays on the line, as the series does it: `Accepted, amended by portalr ADR-0014`.
3. **Change its row** in the folder's `README.md` table to the same status.
4. **On Accepted:** each decision the RFC leaves to be made is recorded as an ADR, in the series of the package it binds, when it is made (the `new-adr` skill). Add each as an item of the RFC's `## Tracking` section, unticked until it lands.
5. **Ticking Tracking items:** tick one only when the pull request that does it has merged, and link what did it (the ADR, the pull request), as the items already ticked do.
6. **On Implemented:** every Tracking item is ticked, or says why it was dropped. If not, report what's left rather than changing the status.
7. **On Superseded:** the new RFC exists first; then link it in the Status line, in both directions.
8. **Check** with `moon run lattice:docs`.

To report where an RFC stands, give its status, its Tracking items still open, and the ADRs it has led to.
