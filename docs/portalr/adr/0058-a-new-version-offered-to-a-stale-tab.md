# ADR-0058: A new version offered to a stale tab

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

A tab opened before a deploy keeps running the build it loaded. The owner opened a thread in such a tab after mini apps had shipped and saw nothing of the app the agent made: the old build had no inline entry for it. Nothing told them to reload.

## Decision

- **A UI's build is its page's entry script.** Vite names it by its content's hash (`assets/index-<hash>.js`), so the page the UI is served as names its build, with no version to keep in step. `useNewVersion(page)` reads the tab's own page and the served one, every five minutes and whenever the tab comes back into view (`focus`, `visibilitychange`); a different entry is a new build. A page with no built entry, as in development, is never compared. Both UIs run it, at their own base.
- **The person chooses.** `NewVersion` says "A new version of portalr is ready. Reload to use it." in a `status` region near the top, with "Not now" and "Reload", reachable by the keyboard, and without motion. Nothing reloads by itself, so a half-filled form or an unsaved edit is never lost; "Not now" holds for that build, kept in the browser's storage, and a later build is offered again.

## Consequences

- Easier: a tab that outlived a deploy says so within five minutes, or as soon as it is looked at again.
- Harder: each open tab reads its UI's page every five minutes, a few kilobytes, and on each return to it.
