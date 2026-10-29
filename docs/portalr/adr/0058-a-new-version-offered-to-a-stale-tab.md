# ADR-0058: A new version offered to a stale tab

**Status:** Accepted, amended 2026-10-28 (see Amendment: a tab whose build is gone)
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

A tab opened before a deploy keeps running the build it loaded. The owner opened a thread in such a tab after mini apps had shipped and saw nothing of the app the agent made: the old build had no inline entry for it. Nothing told them to reload.

## Decision

- **A UI's build is its page's entry script.** Vite names it by its content's hash (`<base>assets/index-<hash>.js`), so the page the UI is served as names its build, with no version to keep in step. The tab's own entry is read from its document; the served page is read again with `no-store` every five minutes and whenever the tab is shown again (`visibilitychange`). Only an answer that is ok, not redirected and HTML, whose entry is under the UI's own `assets/`, names a build: a sign-in page, a captive portal or a failing server never does. In development the entry is the source (`src/main.tsx`), under no `assets/`, so nothing is compared.
- **A build is new once it is read twice running,** so a rolling deploy or a rollback that flaps between two builds is never offered mid-flight.
- **The person chooses.** `NewVersionOffer` keeps an empty polite live region (`aria-live`, not a `status`, so the page's own statuses stay the only ones) on a built page from its first render, so what appears in it is announced; a new build puts `NewVersion` in it: "A new version of portalr is ready. Reload to use it." ("portalr admin" in the admin, the name the shell's mark has), with "Not now" and "Reload", keyboard buttons, without motion. It sits below a narrow window's bar and the skip link, and lets clicks through where it draws nothing. "Not now" holds for that build in that UI, kept in the browser's storage under the UI's address and heard by its other tabs; a later build is offered again.
- **Nothing reloads by itself, and what is half written is asked about first.** "Reload" is the person's. A message drafted in a thread's composer and not yet sent, and the native file editor's unsaved changes, each guard the page (`beforeunload`), so the browser asks before either is lost. A form's fields have no guard: what was typed in one is lost by a reload, as by any other.
- **The keyboard keeps its place.** The region follows the page in the document, so the skip link stays the first stop. "Not now" leaves the focus in the region, not on the page's body.
- **Its look is tokens.** `--notice-*` in `tokens.css`: where it sits, below a narrow window's bar (`--notice-top`), its inset, width, corners, padding and shadow.
- **Its address is the UI's base.** A relative base (`./`) still works: the page is read relative to the tab's address, and its entry is looked for under `./assets/`.

## Consequences

- Easier: a tab that outlived a deploy says so within five minutes, or as soon as it is looked at again.
- Harder: each open tab reads its UI's page every five minutes, a few kilobytes, and on each return to it.

## Amendment, 2026-10-28: a tab whose build is gone

A tab left open across a redeploy asked for the old build's chunks, which the new one no longer has: the server answered 404, and each part loaded on demand failed in its own words, a blank file preview, "The app read no outline from this file", "Its words couldn't be read" ([#1059](https://github.com/alexnodeland/lattice/issues/1059)). Nothing was wrong but the tab's build, and the offer above could be up to five minutes away.

- **A chunk that fails to load reads the page at once.** Vite's preload helper wraps every dynamic import in both UIs, the routes' split components and the add-ons alike, and dispatches `vite:preloadError` when the chunk itself or what it preloads fails to load. `NewVersionOffer` listens for it and reads the page then, with no second read, in a hidden tab too, so a failure while the tab is in the background is told as it is shown: a build other than the tab's is the cause.
- **It is said as what it is, with Reload alone.** "portalr was updated. Reload to continue." ("portalr admin" in the admin), in the same region, with the same Reload, and no "Not now": the tab can't go on, so a "Not now" said to that build doesn't hold it back. Once told, it stays: a later read keeps it so, even one that finds the tab's own build again, as after a rollback, where the chunk that failed is still the one that failed; Reload is then harmless.
- **Offline, or with the server restarting, nothing is said.** The read then names no other build, and the feature's own error stands, as it would for any failed read.
- **The import still fails.** The event is not cancelled: cancelled, Vite resolves the import to nothing, and the feature would fail in a newer, stranger way. The notice sits above the feature's own error, which the reload clears.
- **A thread's draft survives the reload.** The composer keeps its unsent words in the tab's session storage, under the tenant, the person and the thread (or, on the Threads page, the workspace), and takes them back as it mounts; a message on its way stays kept until the server answers, so a reload meanwhile brings it back (and, if it was in fact posted, it is there twice to choose from); they are let go once it is answered, or cleared. Signing out, here or in another tab, or the session ending, lets go of every draft the tab keeps, so whoever signs in next in it finds none. Each thread's page starts with its own draft. Reload, chosen in the notice or the offer, tells the page first (`portalr:reload`), and a composer whose draft is kept lets the page go without the browser's question; one that keeps nothing still asks. Closing the tab still asks, as session storage goes with the tab. A file still uploading asks too, Reload included, as it isn't kept.
- **A route's own chunk reloads once by itself.** TanStack Router's `lazyRouteComponent` reloads the page once when a route's chunk is not found, before this notice is seen; the draft survives that too, though the browser asks first. That is the library's, and is left as it is.
- **The page is never cached, and the old chunks are not kept.** portalr's router already serves the page `no-cache`, with an `ETag`, and the hashed assets `immutable`, so a reload always finds the new build. The old chunks are gone with the old wheel; keeping them for a while would need a store outside the package, which a deployment of a wheel doesn't have.
- **It costs the first page about a hundred bytes.** The listener and the notice's words are in the offer, and letting drafts go is in the session's client, both already in both UIs' first chunk. The draft is the composer's, which is loaded with the thread.
