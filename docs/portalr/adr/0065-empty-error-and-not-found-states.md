# ADR-0065: Empty, error and not-found states

**Status:** Accepted
**Date:** 2026-10-21
**Deciders:** Alex Nodeland

## Context

The UI audit of 2026-10-20 ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md)) found that states with nothing to show were built three ways:

- admin's read failures had their own `ReadFailed` built from `EmptyState`.
- app's missing artifact or rule was a bare page title and a sentence, with no way on.
- The plain pages for a failed start linked home with a raw `<a>`, which kept both `main.tsx` files on Biome's raw-element exception list.

None of these moved the focus when it replaced the page the reader asked for. This is polish PR 7 of the audit.

## Decision

- **`EmptyState`** is the kit's one state. It has a heading, a sentence, and one action, and no illustration. A state that stands in for the page the reader asked for, such as a not-found, takes `focus`: its heading gets `tabIndex={-1}` and the focus on mount, so the keyboard and a screen reader start there. An empty list keeps the focus where it is.
- **`ErrorState`** is a failed read where its content would be. It is an `EmptyState` with `focus`, the failure in an error `Alert` (which interrupts a screen reader), and "Try again" as its action. A screen may add a second way on, such as clearing a filter. admin's `ReadFailed` is now its frame's header plus an `ErrorState`.
- **Not found, in the frame:**
  - In app, a missing artifact or rule shows its section's page header and an `EmptyState` with `focus`, linking back to the list.
  - In admin, the not-founds that say a part isn't yours to read take `focus`.
- **Plain pages** (outside the frame: not found, something went wrong, a tenant you don't administer, a failed start) keep the page's `h1` as their heading and end in one link. "Something went wrong" now offers "Start again". `Plain`'s `home` may be an address, for the failed start, which has no router. That removes the raw `<a>`, so both `main.tsx` files leave the exception list.
- **An upload's refusal names what is taken.** "notes.txt isn't a kind of file this workspace takes: it takes .docx, .dwg, .dxf, or .fcproj." The extensions are the enabled kinds' from `GET …/uploads`, as the server spells them. Each is named once: of spellings that differ only by case, the first is kept. A list longer than six names five and says how many more ("or 4 more"). A workspace that takes none says only the first sentence.

## Announcement and the failure's words

- **Heard twice, by choice.** An `ErrorState` moves the focus to its heading, and its failure is an `alert`. Some screen readers announce both: the heading as the focus lands, then the alert. We chose this over dropping either. The focus tells a keyboard reader where they are. The alert is heard even where the focus isn't followed.
- **A reader sees the kit's words for a failure, never the server's** ([#552](https://github.com/alexnodeland/lattice/issues/552), decided 2026-10-22). `failureSaid` picks a sentence by the refusal's known reason code (`forbidden`, `not_found`, `not_enabled`, `invalid_state`, `version_conflict`, `validation_failed`), then by its status (401, 403, 404, 422, 429, 5xx), else a generic one. `FailureAlert`, which `ErrorState` and the apps' error boundaries use, writes the whole failure to the console for operators once, after the render, as one line: hidden characters out, what looks like a secret redacted, cut between graphemes. Other screens that still show an error's message (the boot failure, the audit log's paging and the deployment audit, the tools page, the confirm dialog, a run's command refusals, a form's rejection message, sign-in) are #552's remaining scope.

## Consequences

- Easier: a kit styles every empty, failed and missing state through one component. A reader landing on one is told so first.
- Inline failures inside a card, a form or a message, which don't replace the page, stay `Alert`s.
