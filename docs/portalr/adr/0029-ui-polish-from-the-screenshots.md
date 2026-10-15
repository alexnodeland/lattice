# ADR-0029: UI polish from the screenshots: one width rule, titles, a violet focus ring

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland

## Context

Screenshots of main on 2026-10-13, light and dark, wide and on a phone, showed small faults across the app and admin (issue #189). Three of them needed a rule, not a fix:

- pages used different content widths, so a page's actions sat at different places from page to page;
- artifacts were named by their ids, `art_a258b71d5c18254e`, in lists, headings and links;
- the focus ring in the dark scheme was cyan, the one colour outside the brand's inks.

## Decision

- **One width rule per page type.**
  - A reading page is one column of 760px (`max-w-190`), its header included, so its actions line up with its content. Thread, Artifact, Rule and Proposals are reading pages.
  - A page of rows or a table uses the frame's full width: Threads, Artifacts, Runs, Rules, and each of admin's.
  - Artifact's open proposals sit in its column, under the content, not in a column of their own.
- **The workspaces page is in the frame.** The tenant's page of workspaces uses the app's frame like every other page: the mark, a switcher that names the tenant alone, and the account. Each workspace is a card with its name, which opens it, and a link to each of its areas. Nothing is read per workspace: grantr and artifactr give no description of one, and a read each would be a request for every card. What isn't known isn't shown.
- **An artifact has a title, and its id beside it.**
  - A renderer says `title(data)`: a note's first line of words, without Markdown's marks; JSON's `title` field, as written. It is pure, cheap, and null for data of any shape that hold none. It never throws.
  - A title is at most 80 code points, the ellipsis that marks a cut one included. Only paired marks are stripped from Markdown, so `my_file_name` and `2*3` stay as written. Every pattern is bounded, and none reads more than 400 characters of a line, so a hostile line is quick.
  - The Artifacts list and an artifact's page show the title, and the id as muted meta. Where there is no title, the id stands in, in the mono face, as before.
  - The list reads artifactr's artifacts, whose data carries what the title is made from; the stream's log doesn't. The route's loader reads them, so no id turns into a title as the page opens; where they can't be read, the page shows ids. The list's rows come from the log, live, and the titles from this read: an artifact the log says was made or changed makes the read stale (`client`'s `stale`), and it is read again, so a title follows its artifact.
- **The focus ring is the brand's violet in both schemes:** `--focus` in the dark scheme is `#a77bdf`, not cyan. It is 3:1 or more on the paper, the surface and the wash, which the token test holds, and a second test holds that its hue is violet's, 255° to 285°, in each scheme.
- **A menu is edged**, as a control is: a menu's popup takes `--edge`, so it stands against the rail in the dark scheme, where `--line` alone didn't.
- **The phone's drawer holds the switcher and the account,** with its name shown, as well as the navigation. The bar behind it keeps its own, which shows an avatar alone. A page with no areas to go between, the workspaces page, leaves the navigation out, and its rail holds the mark, the switcher and the account.
- **A tab's focus ring is drawn inside it.** Access's tab row scrolls, which clips what is drawn outside it, so a tab's outline has a negative offset.
- **Smaller faults:**
  - A rule's JSON wraps inside its box; the install textarea scrolls sideways, and keeps its indentation.
  - A rule's row keeps its state and how far behind it is on one line.
  - Access's tabs are one row, which scrolls on a phone.
  - A failure's message starts with a capital where it starts a sentence: "The server refused the read". `ui`'s `failureSaid` does it for both UIs; a message that follows a colon, as the app's start-up failure's does, is left as it is.
  - The grant dialogs name a person by their id alone, and anyone else for what they are: "Make bob admin of acme?", "Make the group ops admin of acme?", "Revoke admin from the service principal ci?". A person and a service principal may share an id.
  - Home's Failed turns card says "agent turns in the last day", and, on hover, that a rule's run that fails isn't counted.
  - The test application's scripted model proposes a note about what the person asked, so two proposals aren't one.

## Options considered

| Option | For | Against |
|---|---|---|
| **One column for a reading page, the frame's width for a list (chosen)** | A rule a page's type decides | Artifact loses its side column of proposals |
| One width everywhere | Simplest | A table is cramped, a paragraph is long |
| A card per workspace with a read each | A description, a count | A request per card for what grantr and artifactr don't give |
| **A title from the data, by the renderer (chosen)** | Names what people made | The list reads each artifact's data |
| A title in artifactr's own metadata | One field, one place | A change to the protocol for a cosmetic need |

## Consequences

- Easier: a page's width follows from its type, and an artifact is named as people name it.
- Harder: a kind with no `title` is named by its id until its renderer gives one.
