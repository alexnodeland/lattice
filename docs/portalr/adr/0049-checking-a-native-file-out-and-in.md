# ADR-0049: Checking a native file out and in: the editor on its own origin, an upload with its progress, and a retry that is safe

**Status:** Accepted, amended 2026-10-23 (the chooser's own button)
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#people-check-out-and-check-in) has people edit a Word document in WordCraft's browser build, unmodified, at its talk level 1: it opens a file from the person's disk and saves one there, and nothing else. So:

1. **Check-out.** portalr creates the check-out and its lease, downloads the head, and opens the hosted editor in a new tab, showing the expiry.
2. **Editing.** The person opens the downloaded file in the editor, edits it, and saves it to disk.
3. **Check-in.** The person uploads the file in portalr. The router streams it, and commits a revision as the person, with `source: "check_in"`, or keeps it as a proposal if the file moved on meanwhile, and releases the lease.

`files_router` serves the check-out, its extension and the check-in, and tells the check-out's own holder its id and every reader the largest check-in it takes ([native files ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md), [ADR-0008](../../artifactr/files/adr/0008-what-portalr-reads-of-a-native-file.md)). `editor_app` serves the build on an origin of its own, under a policy of its own. [ADR-0048](0048-native-files-in-the-app.md) put the file's section on its artifact's page.

## Decision

- **`config.json` names each app's hosted editor,** as `editors`, by the app's integration: `Site(editors={"files:wordcraft": "https://wordcraft.example.net/"})`. `Site` refuses a key that isn't a native file's app, `files:<app>` in an integration key's form, and an address that isn't `https`, or `http` on loopback for tests, or that carries a user or a password. The app opens none that is on the portal's own origin, which would put a third party's build beside the session: the editor must be on a host for which the portal sets no cookies, as RFC-0003 has it. portalr's own policy doesn't change: the editor is another origin, which the app only links to.
- **Checking out, while no one has the file:** "Check out and open WordCraft" sends the check-out, then opens the editor in a new tab with `noopener,noreferrer`, still within the click's activation, downloads the head the check-out holds, under the file's name, and says so: until when, and that the editor opened, or, since `noopener` hides whether a blocker took it, to use "Open WordCraft". The editor holds no handle on the portal's window, and the editor's `same-origin` opener policy keeps the portal's off it. Where no editor is hosted, the button is "Check out and download", and says to open the file in the app oneself. Neither opens anything where the check-out is refused.
- **While it is the reader's,** by the check-out's id the status gives its holder alone, so another tab or a reload finds it, or that this tab keeps, in its session storage, from the check-out until it ends, so that it can still be checked in once its lease ran out, when a check-in that finds the file moved on is a proposal: until when, in the reader's time; "Open WordCraft", a link to a new tab, for when a blocker took the first or the tab was closed; "Download again"; "Extend", which renews the lease for its whole length from now; and the check-in.
- **Checking in:**
  - The edited file is chosen through `ui`'s `FileChooser`: a file input named by its label, which the keyboard and assistive technology reach, offering the file's own extension, and around it a zone a file can be dropped on instead, never as the only way. The input is out of sight and the browser draws none of its own button or "No file chosen": a kit button, "Choose a file" or "Choose files", is its second label, shows its focus and opens it, and takes the button's disabled look while a check-in is sent. The chooser no longer shows the chosen file's name: the check-in's status line and the upload list say it (amended 2026-10-23, from issue 214's audit).
  - A file larger than the status's `limit` is refused before it is sent, saying both sizes.
  - It is sent through `client`'s `checkIn`, over `XMLHttpRequest`, which says how far an upload has gone, as `fetch` doesn't, and ends the session where it is refused unsigned, as a command does; `ui`'s `Progress` shows it, a `progressbar` named by what it sends, with its share and its sizes in words. One button checks in, stops, and tries again in turn, so focus stays on it; a stop says what was sent may still have landed.
  - What it made is said, and what came of every action here is focused as it is said, since the control that did it may be gone: "Checked in brief.docx as version 3"; kept as a proposal, as a warning, since the file changed after it was checked out, as where its lease ran out and someone took it, or someone accepted a proposal meanwhile, with a link to the workspace's proposals; or nothing changed, so no version was made, and the check-out has ended.
  - A refusal says why as the reader can act on it: 413, too large; 422, the app couldn't read it, or it isn't a file the kind holds, so check it is the file saved from the app; 503, the app couldn't finish, try again; 409, the server's reason, such as the file held by someone else, the check-out checked in already, or the app switched off, and the workspace's integrations are read again, as a stream's `not_enabled` reads them ([ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md)).
- **A retry is safe, so it is offered:** where nothing answered (the connection dropped, or the reader stopped it, status 0) or the app couldn't finish (503), "Try again" sends the same file. Sent again, a file never makes anything twice: one that landed as a version answers `unchanged`, said as "checked in already: nothing new was made"; one that landed as a proposal is refused as checked in already (`invalid_state`), said as "checked in already, as a proposal". The check-in stays on the page while its answer is unknown, though the lease it held is gone.
- **The page reminds the person** that their downloaded copy stays on their computer after the check-in, for a shared one. Nothing on the page calls the editor or the app's reading of a file a sandbox: in a deployment without RFC-0003's worker, the server reads each file through `Subprocess`, for trusted files only.
- **An agent's edit,** which holds the file for seconds, offers no check-out, and says it can be checked out once the edit is done; the status is read again every two seconds meanwhile (ADR-0048).
- **Tests:** `client`'s for the commands and `checkIn`, over a stand-in `XMLHttpRequest`; `ui`'s for `FileChooser`, dropped and chosen, and `Progress`, with axe, and `check-in.screenshot.test.tsx` in every scheme and mode; and the app's route tests for checking out, extending, checking in with progress, a refusal, a file too large, and a retry that finds it checked in.

## Options considered

| Option | For | Against |
|---|---|---|
| **The editor opened once the check-out is made (chosen), with a link to open it again** | Nothing opens for a check-out refused | A strict blocker may take the tab, and the link is the way |
| The editor opened at the click, before the check-out | No blocker takes it | A tab for a check-out that may be refused |
| The editor in a frame of the portal | One tab | A frame gains nothing without a host bridge, and the build's policy refuses one (`frame-ancestors 'none'`) |
| **`XMLHttpRequest` for the check-in (chosen)** | Its upload's progress | One request not through openapi-fetch |
| `fetch` with a streamed body | One client | No upload progress, and streamed bodies need HTTP/2 and duplex half in Chromium alone |
| **"Try again" with the same file (chosen)** | A dropped answer costs one press, and the server makes nothing twice | None found |

## Consequences

- Easier: a person checks a file out, edits it in WordCraft as released, and checks it in, with what came of it said, and a dropped connection retried safely.
- Harder: an application hosts the editor on a host name of its own, and names it in `Site`; until it does, people open the downloaded file in an app of their own.
- Revisit: talk level 2, a host bridge, once `storytold/wordcraft#405` or `#1655` ships in a release, which would let the portal hand the file to the editor and take it back without the person's disk.

## Action items

1. [x] `Site.editors` and `config.json`'s; `client`'s check-out, extension and `checkIn`; `ui`'s `FileChooser` and `Progress`; the app's check-out and check-in.
2. [x] The RFC's scenarios, with the editor served on an origin of its own ([ADR-0050](0050-a-native-files-proposals-and-the-pilots-scenarios.md)).
