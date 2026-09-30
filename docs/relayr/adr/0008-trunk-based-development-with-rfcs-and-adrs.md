# ADR-0008: Trunk-based development with RFCs, ADRs and evergreen docs

**Status:** Accepted, amended by [ADR-0013](0013-relayr-in-lattice.md)
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

relayr is built in the open, in small steps, by a small team and agents working in parallel, as its siblings are ([artifactr ADR-0014][a-adr-0014], [reflexr ADR-0012][r-adr-0012], [evalr ADR-0004][e-adr-0004]). Its design lives in another repository's RFC ([stackr RFC-0002][rfc-0002]), so the decisions and the plan need a home next to the code.

## Decision

- **Trunk-based development.** `main` is the trunk and is always releasable. Work happens on short-lived branches cut from the latest `main`, merged as small pull requests within a day or two. No stacked branches.
- **Squash merges with Conventional Commit titles**, so `main` has one commit per change and git-cliff generates the changelog from history.
- **CI gates every merge** ([ADR-0009](0009-quality-gates.md)).
- **RFCs before substantial changes**, in [`docs/rfcs/`](../rfcs/README.md). Multi-PR work is tracked in its RFC's checklist; [RFC-0001](../rfcs/0001-v0.1-implementation-plan.md) carries stackr RFC-0002's phases as relayr's plan.
- **ADRs for decisions**, including the decisions stackr RFC-0002 made for relayr (ADR-0001 to ADR-0007) and those made while building. Accepted ADRs are immutable; a changed decision gets a new ADR that amends or supersedes the old one.
- **Evergreen architecture docs.** `architecture.md` describes relayr as it is, and a pull request that changes described behaviour updates it in the same pull request.

## Consequences

- Easier: every commit on `main` is a reviewed, releasable change, and the reasoning behind it survives in the repository.
- Harder: every behaviour change carries a documentation obligation in the same pull request, and large work must be sliced into steps that each leave `main` green.

[a-adr-0014]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0014-trunk-based-development-with-rfcs-and-adrs.md
[e-adr-0004]: https://github.com/alexnodeland/evalr/blob/main/docs/adr/0004-trunk-based-development-with-rfcs-and-adrs.md
[r-adr-0012]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0012-trunk-based-development-with-rfcs-and-adrs.md
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md
