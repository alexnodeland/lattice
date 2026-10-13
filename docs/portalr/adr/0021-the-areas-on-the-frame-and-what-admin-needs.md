# ADR-0021: The areas on the frame, a danger colour, budget badges, and what admin's frame decides

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0019](0019-the-kits-look.md) gave `ui` its look and its frame, but no area used them: each still rendered a `Page` with a plain list. The Rules area ([ADR-0020](0020-the-rules-area.md)) completed the app's areas. Mockups of the admin UI in the same frame then raised questions the app's choices didn't answer:

- what a destructive action looks like;
- how a budget's state is shown;
- what colour a chart may use;
- what an operator sees with no tenant chosen.

The maintainer decided each of them.

## Decision

### The app's areas are on the frame

- **A workspace's routes render `AppShell`.**
  - The `Switcher` lists the person's tenants, from their memberships, and the workspaces grantr lets them open. Its menu also links to every workspace in the tenant.
  - A `SideNav` holds Threads, Artifacts, Proposals, Runs and Rules, each with its Lucide icon beside its word. Threads counts the turns paused for an answer, and Proposals the open proposals.
  - The `AccountMenu` holds sign-out and the person's scheme. The scheme is kept in localStorage and set as `data-theme` before the app renders.
  - The workspace's streams wrap the frame, so the counts follow the log.
- **Outside a workspace, ui's `Plain` page frames the screen:** the lockup as a link home, and one column. Choosing a tenant or a workspace also shows the account; what went wrong, with no one known, shows none. Signing in is a card. `Page` retires, and the page's background and text colour are the `html` element's.
- **Each area opens with a `PageHeader`** whose one heading is the area or the item.
  - **Lists are ui's lined `Rows`,** each row's link stretched over the row: threads (with the status of a run that is going or waits), artifacts, rules and schedules. An area with nothing in it says so with an `EmptyState`. A section under the page's heading opens with a `SectionTitle`.
  - **One rhythm from header to content:** the frame's column sets one gap between a page's header and each part under it, the same in every area.
  - **Runs is two `Table`s,** the agent's turns and the rules' runs, each row named for its run, with the Feedback column only for those who may give it. Below the small breakpoint each run is a card instead: its status and title on top, its attempts and feedback under them, and its actions in reach.
  - **An artifact shows** its content in a `Card` and its revisions as cards. On a wide screen, its open proposals sit beside them.
  - **A thread keeps** a 760-pixel measure, and its composer is pinned to the bottom of the view.
  - **Install a rule** is a `Card`.
  - **Archiving a rule** asks first in a `ConfirmDialog`.
- **The scenarios change where a role or a name did, in the step definitions alone:**
  - signing out is the account menu's item;
  - every workspace is the switcher's;
  - an area's title is heading level 1;
  - runs are table rows;
  - archiving confirms;
  - "Opening a workspace" says it is in the workspace rather than on its page.

### A danger colour, for destructive actions alone

- **`--danger` and `--on-danger`** are `light-dark(#9b1c3c, #ff9fb2)` and `light-dark(#ffffff, #17111f)`. **`--danger-hover`** is `--danger` mixed 88% with `--on-danger`. Their contrast is asserted in both schemes:

  | Pair | Light | Dark |
  |---|---|---|
  | `--danger` on paper, surface, wash | 7.35, 8.00, 6.25 | 9.55, 8.89, 7.73 |
  | `--on-danger` on `--danger` | 8.00 | 9.55 |
  | `--on-danger` on `--danger-hover` | 6.34 | 7.61 |

- **They are for deleting, removing, revoking and archiving, and nothing else.** A danger `Button` acts only inside a `ConfirmDialog`.
- **The crimson sits near reflexr's red,** `#B3122E`. It is darker in light and lighter in dark, it isn't an ink, and it appears only on a destructive action's button, never in a mark.
- **`ConfirmDialog`** is a Base UI alert dialog built on `dialog.ts`'s classes, the look every dialog in `ui` shares.
  - It names what will be lost. The focus starts on Cancel, and Escape or Cancel closes it with nothing done.
  - With `typed`, the focus starts in the field, and the action waits until the name is typed, when Enter sends it: deleting a tenant needs its name.
  - An action that fails leaves the dialog open, and says why.

### Budgets, charts, and admin's frame

- **A budget's state is a word and a shape, with no warning colour.** `StatusBadge` gains `near` ("Near budget": a half-filled ring) and `over` ("Over budget": a triangle, the badge in the foreground). It is louder by weight, never by hue.
- **Charts may use the brand's inks as marks, never as text.** Every series also gets a pattern or a direct label, so colour is never the only cue.
- **The admin decisions, which phase 6 builds:**
  - Under "All tenants", an operator sees the Deployment areas (Tenants, Tools) alone, and the tenant areas hide.
  - Deep links into Tempo and Langfuse are hidden from anyone who can't use them.
  - AgentPrism's trace waterfall is restyled to the tokens.
  - On a phone, Access is a list of cards rather than a sideways-scrolling table.
  - The rail's label for feedback and evaluations is "Feedback".
  - The audit log shows absolute times in the viewer's time zone, with the relative time on hover.
  - admin's tenant switch is its own, apart from the app's.
- **admin renders its frame now,** `AppShell` with admin's mark. Its areas and its signing in arrive with phase 6.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Danger | **A token pair, for destructive actions alone (chosen)** | An action that loses work looks unlike every other | One more colour, near reflexr's red |
| | The foreground, bordered | No new colour | A destructive action reads like any secondary one |
| Budget | **A word and a shape (chosen)** | No warning hue to keep apart from danger | Quieter than a colour |
| | A warning colour | Seen at a glance | A third signal hue, and colour carrying meaning |
| Charts | **Inks as marks, with patterns or labels (chosen)** | More than two series stay apart | A pattern per series to design |
| | Accent and greys alone | Fewest colours | Two or three series at most |
| Run lists | **Tables, rows named for the run (chosen)** | Columns line up; the RFC's tables | A step's selectors move from list items to rows |
| | Lined rows | Fewer changes | Status, attempt and actions don't line up |

## Consequences

- Easier: every area, and admin's phase 6, builds on one frame, one set of components and one dialog look.
- Easier: a destructive action can't be taken by one stray click, and is told apart by more than its colour.
- Harder: the danger colour must stay off everything but destructive actions, which review holds.
- Harder: a chart needs a pattern or a label for each series.
