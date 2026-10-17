# ADR-0043: Markdown's basics: code blocks, callouts, footnotes per message, copying, an add-ons seam, and tests under the policy

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** [ADR-0015](0015-the-chat-components-and-streamdown.md), for how Streamdown's code and callouts render

## Context

`ui`'s `Markdown` renders an agent's messages, a `note` artifact and, later, a dashboard's text panel, through Streamdown with its core alone ([ADR-0015](0015-the-chat-components-and-streamdown.md)). Models write more of GitHub's Markdown than it drew well:

- **Fenced code had no language, no copy and no wrap.** Streamdown's own controls use classes portalr's theme doesn't have (`bg-sidebar`, `backdrop-blur`) and their own icons, so they are off.
- **GitHub's callouts showed as quotes.** These are `> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]` and `[!CAUTION]`.
- **Two messages' footnotes shared ids.** Every message's first footnote was `#user-content-fn-1`: remark-rehype's prefix is the same for every message, and Streamdown's sanitizer schema adds none of its own.
- **A message couldn't be copied as it was written.**

Highlighting, math and diagrams are add-ons, each loaded when a message needs it. A workspace will turn some of them off, through an Integrations port, deployment ∧ tenant ∧ workspace, that the Excalidraw RFC is designing and that doesn't exist yet. [ADR-0042](0042-mermaid-cant-draw-under-the-policy.md) parked Mermaid. Nothing yet showed that `Markdown` meets the Content-Security-Policy the UIs are served with: the component tests run under Vite's development server, with no policy.

## Decision

- **Code blocks are `ui`'s own** (`CodeBlock`): `Markdown` gives Streamdown its own `code` component, and Streamdown's controls stay off.
  - A block names its language, or "Code", and has **Wrap**, a toggle (`aria-pressed`), and **Copy**.
  - Copy copies the code as written, never the page. It says "Copied" or "Couldn't copy" on the button and in a polite status: a page with no clipboard, as outside a secure context, is told.
  - The code scrolls sideways in a region that is a tab stop, named "‹language› code", so a keyboard can scroll it. Code is set without the face's ligatures, so `-->` reads as it was typed.
- **One scrolling region, `ScrollRegion`,** serves `Table`, the code block and Markdown's tables, and Biome's override for a tab stop on a section moves to it. Each is a named region and a tab stop whether or not it overflows, so a long thread lists many regions: the cost of a keyboard reaching every one that does.
- **Callouts:**
  - A remark step marks a quote whose first line is a callout's marker, in any case, as an `aside` of that kind, and drops the marker.
  - The sanitizer's schema is Streamdown's, plus that one element with that one attribute and its five values. No HTML in a message reaches it (`skipHtml`).
  - An aside renders as `Alert`, with its word always shown: a note, a tip and an important one in the note's tone, a warning in the warning's, and a caution in the error's. A model's caution looks like one of portalr's own errors: it sits inside the message, under who posted it, and is never announced, which is what tells them apart.
  - `Alert` takes `live={false}`, which makes it a `note`: text a page holds is read as the page is read, never announced as a status.
- **Footnotes are each message's own.** remark-rehype's `clobberPrefix` is React's id for the `Markdown`, in letters and digits (`mdr4-fn-1`), so a reference and its footnote agree within a message and differ between messages. Streamdown caches a processor for each set of options, the hundred most recently used, so each message has one, and a thread longer than that builds a processor again for a message it scrolls back to.
- **A task list's boxes are drawings, not controls:** an icon, and "Done:" or "To do:" in words for a screen reader, since nothing here can tick one.
- **Each message can be copied as Markdown:** `Message` has Copy, which copies the store's `content` as written, never what the page shows.
- **Streaming:**
  - Streamdown completes unfinished syntax with `remend`, but not block math: nothing draws math yet, so a `$$` mid-stream stays as written rather than being closed.
  - A link still streaming is `streamdown:incomplete-link`, which `linkTo` refuses like any other protocol it doesn't allow. A test holds that.
- **The add-ons seam:**
  - What `Markdown` may draw beyond its basics is an `Addons` value, which `AddonsProvider` gives to the Markdown inside it. Today it holds `mermaid`, which is off by default.
  - An add-on's fence that isn't drawn, because it is off or because `ui` can't draw it yet, shows as its source with one quiet line, never as nothing.
  - GitHub's Markdown, code blocks, callouts and copying have no switch.
  - The app will give `AddonsProvider` the Integrations port's effective value when that port exists. That is the seam's other side, and it isn't built here.
  - A switch decides what is drawn, not what is safe: the sanitizer and the policy are the boundary.
- **Tests under the policy** (`web/ui/csp`):
  - **The page:** Vite builds a small page that renders `Markdown`, with the React and Tailwind plugins and the public files app and admin build with, and `vite preview` serves it with the policy in `policy.txt`. A portalr test holds that file to the router's `policy()` for an application with Supabase on a path of its own origin.
  - **The runner:** a Vitest project of its own (`csp`) drives Chromium through Playwright. A listener added before the page's scripts records every `securitypolicyviolation`, and the console's errors are recorded too. Any one fails the test.
  - **The proof it sees:** a first test inserts an inline style and a `<style>`, and expects both reported.
  - **What it checks:** every element whole and streamed a character at a time, Wrap and Copy, a diagram's fence with diagrams off and on, and each message of a hostile corpus.
- **Beside it, in the component tests:**
  - axe finds nothing wrong with every element together.
  - A stream fed a character at a time never shows a mark with words after it (`**bold`) or a link to `streamdown:`.
  - The hostile corpus runs, loads and links nothing.
  - Screenshots pin every element, wide and narrow, in each scheme, in colour-blind mode and under forced colours (`markdown.screenshot.test.tsx`), against Linux baselines made in CI.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Code blocks | **`ui`'s own (chosen)** | Its tokens, words and controls; a place for highlighting | A component to keep |
| | Streamdown's, with its controls | Nothing to write | Classes the theme lacks, its own icons and words |
| Callouts | **A remark step to `Alert` (chosen)** | The tree says what a callout is; one element through the sanitizer | A schema to extend |
| | Reading quotes' text in the `blockquote` component | No schema change | Matching on rendered children |
| The policy | **A built page, served with it (chosen)** | What ships is what is checked | A build in `ui`'s tests, a few seconds |
| | The component tests under a policy | One runner | Vite's development server injects inline styles and scripts, so it can't run under it |
| | app's scenarios | The real application | Docker and the whole stack for a renderer's check |

## Consequences

- Easier: what a model writes in GitHub's Markdown reads as GitHub draws it, and copies as it was written. A change that breaks the policy fails `ui`'s tests, not a reader's page.
- Easier: an add-on loads behind the same seam and is held by the same tests.
- Harder: `ui`'s tests build a page. Each processor for a message's footnotes is cached, so a long thread holds up to a hundred.
- Sizes: the app's are 179.7 / 428.5 / 143.6 kB (initial / total / largest), from 179.3 / 425.3 / 143.6 kB. The ceilings are unchanged.
