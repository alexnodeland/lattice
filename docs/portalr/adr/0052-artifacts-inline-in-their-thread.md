# ADR-0052: Artifacts inline in their thread, a mini app first

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

[ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md) ran a mini app on its artifact's page alone. Asked for a game, the agent made one, and the thread said only that it had: a person had to find the artifact to play it. Forms, dashboards, Markdown, code and charts already have renderers ([ADR-0017](0017-the-artifacts-and-proposals-areas.md)), and will be shown in the thread next.

## Decision

- **The store knows where an artifact was made.** `client`'s `Artifact` keeps the `thread_id` and the `seq` of the first event the store saw of it; later events keep them.
- **A kind's renderer says whether its thread shows it:** `Renderer.inline`. The thread's log interleaves its messages and the artifacts made in it whose kind is `inline`, by `seq`: one entry an artifact, at its latest version, read over REST and again as the log moves past it. Today only `app` is `inline`; another kind is one flag.
- **`InlineArtifact`** is the entry's chrome, in `ui`: named by its title, the kind's renderer inside, and "Open its page", where its revisions and its full view are. The app's `ThreadArtifact` reads it, says "Loading…" or why it couldn't be read, and gives an app its `AppHost` and the kill switch, as the artifact's page does.
- **A running app is sized whole.** The app's document begins with a measure of its own height, as laid out, sent as `ui/notifications/size-changed` with portalr's `measured` whenever it changes, at most every 200 ms, so an app that says nothing, or says a height taken before it was laid out, is still shown whole, and grows and shrinks with what it draws. The app's own height wins from the first it says; one below 120 pixels is no height. An app that fills its window keeps the frame it has, 360 pixels at first.
- **A running app is shown whole.** In the thread, its frame is as tall as the app is, up to twice the window's height, and the page scrolls past it; the frame has nothing to scroll, so a scroll over it passes on to the page. The composer is pinned below the thread, in its flow, so the end of the thread is above it once scrolled to. Only a truly large app scrolls inside its frame; the full view is there for immersive play. *Amended 2026-10-20: a cap of the window less 15rem cut an ordinary game off.*
- **A running app has a full view.** "Full view" makes the frame's box fill the window, as a modal dialog named for the app, with the page behind it inert and the host's label and summary above the frame; "Back to the page", focused first, or Escape in the page returns it. Escape inside the frame is the app's, as every key there is. The frame isn't moved, so the app runs on, and its host context's `displayMode` says `fullscreen` or `inline`.
- **stackr's template runs apps out of the box:** `PORTAL_URL` and `PORTAL_APPS_URL` name the portal's origin and the apps', `Site(apps=)` and `SandboxOrigin` are wired from them, compose publishes the apps' origin on the next port, `ui:mini-apps` is installed (off until a tenant or workspace switches it on), and the UIs' build copies the sandbox page beside them.

## Consequences

- Easier: an app the agent makes or updates is played where it was asked for, live, and one instance at a time.
- Easier: a later kind is shown inline by setting `inline` on its renderer.
- Harder: a thread with many apps runs each at once, a frame, a sandbox and a bridge apiece, each reading the integrations every half minute; the kill switch and archiving stop them all.
- Harder: `make serve` listens on one port, so apps run under `make up` until it listens on two.
