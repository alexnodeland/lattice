---
name: review-context
description: Find the ADRs, RFCs and architecture docs that govern the files a lattice change touches, and summarize what they require of it. Use before changing a module you haven't worked in, when reviewing a branch or a pull request, or when asked which decisions apply to some code.
---

# The decisions behind a change

lattice has hundreds of ADRs, in a series for each package; the ones that bind a change are rarely the ones whose titles come to mind. Find them before writing or reviewing the code.

1. **The files.** For a branch, `git diff --name-only origin/main...HEAD`; for a pull request, `gh pr diff <n> --name-only`; or the paths you are about to change.
2. **Their packages and modules.** `packages/<pkg>/src/<pkg>/<module>/...` belongs to `<pkg>`'s `<module>`; `packages/portalr/web/<name>/` to portalr; `examples/<name>/` to the library it implements (docplan: artifactr, oncall: reflexr); `.github/`, `scripts/`, `.moon/` and the root's files to lattice's own series. artifactr's `files` module has its own series in `docs/artifactr/files/`.
3. **The governing documents,** for each package:
   - its architecture doc, `docs/<pkg>/architecture.md` (`docs/architecture.md` for lattice), whose section for the module says what exists;
   - its ADRs that name the module or its files: `grep -rlE '<module>|<file stem>' docs/<pkg>/adr/`, then the series' `README.md` table for their status;
   - the RFCs still open over it: `docs/<pkg>/rfcs/` and `docs/rfcs/` with a status of Draft, Discussion or Accepted, and the unticked items of their Tracking sections;
   - lattice's cross-cutting ADRs that apply to every package (`docs/adr/`: quality gates, settings, lattice-core, extras), when the change is of their kind.
4. **Follow the chain.** An ADR whose Status says superseded or amended points at the one that now holds; read that one, and its amendment sections, rather than the original.
5. **Report** a short list: each document, by its series ("reflexr ADR-0041"), with a relative link and one line on what it requires of this change. Lead with any the change seems to contradict. Leave out documents that only mention the module in passing.

Read the documents before quoting them. If no decision covers the change and it makes one, say so: it may need an ADR (the `new-adr` skill).
