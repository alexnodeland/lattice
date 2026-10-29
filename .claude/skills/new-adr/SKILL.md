---
name: new-adr
description: Write a new ADR or RFC in lattice, in the right series, with the next number, from the template, listed in the series' README and in the site's nav. Use when a decision is made (ADR) or a substantial change is proposed (RFC), or when asked to record, supersede or amend a decision.
---

# A new ADR or RFC

1. **Pick the series.** A decision within one package goes in `docs/<package>/adr/` (an RFC in `docs/<package>/rfcs/`). One that spans packages, or is about the repository, CI or releases, goes in `docs/adr/` (`docs/rfcs/`). artifactr's native files have their own series, in `docs/artifactr/files/adr/`.
2. **Number it.** The next number is one more than the highest `NNNN-*.md` in that folder, four digits. Name the file `NNNN-<a-sentence-of-the-decision>.md`, lower case, words joined by `-`, as the neighbours are.
3. **Write it from the template:** `docs/adr/template.md` or `docs/rfcs/template.md`. Status `Proposed` unless the user says the decision is made; today's date. Write the title as the decision, not the topic ("A merge queue on Mergify", not "Merge queues").
4. **Refer to others with their series** outside their own: "reflexr ADR-0003", "lattice RFC-0002", with relative links.
5. **List it** in the folder's `README.md` table (number, title, status), and add the path to the folder's section of the nav: `docs/.nav.yml` for lattice's own, `docs/<package>/.nav.yml` for a package's. A page missing from the nav is left out of the site's sections.
6. **Superseding or amending:** never edit an accepted ADR's body. Write the new one, then change only the old one's **Status** line (`Superseded by ADR-NNNN`, or `Accepted, amended by NNNN`) and its row in the README.
7. **Check:** `moon run lattice:docs`. A list needs a blank line before it, and nested items are indented by their parent's text.

If the decision changes what exists, update `docs/<package>/architecture.md` in the same pull request.
