# ADR-0068: Where the focus goes, and one not-found

**Status:** Proposed
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

## Context

The accessibility audit of 2026-10-22 (WCAG 2.2 AA) found five places where the focus was lost or taken, and not-found pages built three ways:

- **S1:** Tab left the phone's drawer, a full view, and Share, for the document or the page behind.
- **S2:** after a navigation inside the app, the focus fell to the document's body.
- **S3:** Download disabled itself while it went, which dropped the focus.
- **S5:** a question already waiting took the focus when its thread opened, skipping the page's heading and the messages that explain it.
- **S8:** an unknown tenant showed "Something went wrong" with a raw 403. An unknown artifact kept the list's heading. admin's unknown page drew a second `main` inside its frame, and said "Not a tenant you administer" of a tenant the reader administers.

ADR-0055, ADR-0058 and ADR-0059 set no rule for any of these.

## Decision

- **After a navigation, the focus goes to the new page's `h1`,** where the focus was lost: to the document's body, as it is when the link followed went with its page.
  - `useHeadingAfterNavigation` in ui subscribes to the router's `onResolved`. When the path changed, two frames later, it focuses `#main h1`, with `tabIndex=-1` and no ring.
  - The first load starts at the document, as a browser's does, so a plain page's heading isn't focused on a first load.
  - Focus that is still somewhere stays there: a rail's or a drawer's link that stays, or a page that placed it itself.
  - app's and admin's root routes use it.
- **A full view keeps Tab inside it:** from its last stop to its first, and Shift+Tab back, as a modal dialog does. Its stops are what Tab reaches:
  - in the order, and enabled;
  - drawn, so not hidden and not inside a closed `<details>`;
  - a `<details>`' summary;
  - of a group of radios, the checked one, or the first.
- **The drawer's and Share's escape wasn't reproduced.** On this Base UI version, in Chromium, Tab and Shift+Tab stay inside the phone's drawer and inside Share, whether Share is opened alone or from the thread's menu. Tests now hold both.
  - The kit's `Dialog`, which Share uses, now says `aria-modal="true"`, as the drawer already did. `ConfirmDialog` is Base UI's `AlertDialog`, and is left as it is.
- **A download keeps the focus.**
  - Its button is `focusableWhenDisabled` while it goes. Pressed again, it starts nothing more.
  - "Downloading…" is said in a polite status.
  - A download the person started is tried again once, not as often as a read the page makes itself, so its failure is said within seconds.
  - The file page's button carries no `aria-busy`, which belongs to regions and may quiet the name's change. The inline header's icon button keeps the one it had.
- **A question waiting when its thread opens leaves the focus be.**
  - The page lands on its heading. "Go to the question" in the header takes the focus to the question's own named part, its form "The agent asks".
  - A request that arrives while the page is open still takes the focus, as before.
  - What was waiting is kept with the thread's id, so another thread's page starts afresh.
- **One not-found, `NotFound` in ui:** an `h1` naming what is missing, which takes the focus; a sentence on why it may be; and one link on. The window's title says the same.
  - In the frame, it is used for an artifact, a rule, a thread, and admin's unknown page.
  - An unknown page under a tenant is its own catch-all route, `$tenant/$.tsx`, in app and in admin. admin's renders inside the frame's own `main`.
  - So the tenant's not-found means one thing only, without a flag:
    - a tenant the reader isn't a member of, which grantr refuses as 403, is "Tenant not found" on a plain page in app;
    - a tenant they don't administer stays admin's own plain page.
  - This replaces ADR-0065's `PageHeader` with an `EmptyState` beneath, for not-founds that stand in for a page. The empty and error states stay ADR-0065's.

## Consequences

- Easier: a keyboard or screen-reader user who follows a link starts at the new page's heading. No page drops them at the document, and none takes them past what explains a question.
- Harder: a page that moves the focus itself must do it before the second frame after a navigation, or the heading gets it first. Today's (a not-found's heading, an error state's) run as they mount.
- The app stays within the ceilings [ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md) sets after #662's cut.
- Not done here:
  - a thread's window title when it isn't found, which only the page learns, after the stream is live;
  - an artifact's window title by its name, since naming it in the route's head would pull every renderer into the first load;
  - Share's first focus on its heading, which would change every dialog the kit's `Dialog` opens.
