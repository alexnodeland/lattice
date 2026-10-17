# ADR-0015: The chat's components, and Markdown through Streamdown

**Status:** Accepted, amended by [ADR-0043](0043-markdowns-basics.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives `ui` the chat: the message list, streaming Markdown, the composer, tool-call and approval cards, proposal cards with accept and reject, and run status, rendering what `client`'s stores hold and knowing nothing of the transport. An agent's messages are Markdown, streamed a few characters at a time, so a renderer sees unfinished syntax: an open `**`, half a table, a fence without its end. They are also text a model wrote, which may repeat what a document or a person put in front of it: raw HTML, a `javascript:` link, an image that reports who loaded it.

## Decision

- **Streamdown renders Markdown,** pinned at 2.7.0, a 2.x release from Vercel that completes unfinished syntax as it streams. Only its core is installed: no code highlighting, Mermaid or math plugins, whose bundles the chat doesn't need yet. Tailwind finds its classes through an `@source` line in `ui`'s `styles.css`, where the names they use (`primary`, `border`, `muted-foreground` and the like) are portalr's roles; inline code and a table's head, whose background Streamdown names `muted`, which is portalr's quiet text, are `ui`'s own. Its plugins are built once, since it renders a block again whenever they change.
- **No raw HTML.** Streamdown passes HTML through by default, sanitized; `ui`'s `Markdown` drops `rehype-raw`, so a `<script>`, a `<b>` or any other element shows as the text it is.
- **Links go to the web or to mail alone,** or to this page or application. `ui` renders every link itself, rather than through `rehype-harden`, whose allow-list compares against a URL's protocol with its colon and so lets `xmpp:` and `blob:` through: anything but `https:`, `http:` and `mailto:` is no link at all, such as `javascript:`, `data:` or `vbscript:`. A link away from the application opens apart from it, with `rel="noopener noreferrer"`; a link to a place on the page stays in it.
- **Images from other origins are blocked, not proxied.** The router's Content-Security-Policy allows the application's own images alone, and `ui` shows any other as "Image blocked", rather than letting the browser refuse it silently. A proxy would be a server route of its own, for images no agent here needs to show.
- **The components render `client`'s store,** typed by it: a `Message`, its `Feedback`, a `Run`'s `Tool`s and its `DeferredRequest`s, a `Proposal`. They import its types alone, and a root test fails on any import from `@portalr/client` in `ui` that isn't `import type`, so `ui` never calls the server and `client` stays out of its build. Each command a part can send is a callback: the composer's message, an approval or an answer, accept or reject, thumbs on a message. The app sends them. What a person's thumbs are is `client`'s, a selector over the store. The messages are a log, announced as they come; a paused run's request takes the focus as it appears, and answers once.
- **The store keeps what the chat shows:** a paused run's requests until each is answered, a proposal's change, rationale and run, and the feedback on each message.

## Options considered

| Option | For | Against |
|---|---|---|
| **Streamdown (chosen)** | Built for streamed Markdown | Its defaults pass HTML through and open every link apart, which `ui` turns off |
| react-markdown with remark-gfm | Smaller; no HTML unless asked | Renders unfinished syntax as it is, so a streamed `**` flickers until it closes |
| **Block other origins' images (chosen)** | Matches the CSP; nothing to run | An agent's image from elsewhere doesn't show |
| Proxy them through the application | They show | A route that fetches what a model names: a server-side request forgery to guard |
| **Components typed by `client` (chosen)** | One shape for the store and the screen | `ui` depends on `client`, for types |
| View shapes of `ui`'s own, mapped by the app | No dependency | A second model of messages and runs to keep in step |

## Consequences

- Easier: what an agent streams reads as Markdown at once, and nothing it writes runs in the page.
- Harder: an image an agent links from another origin shows as blocked.
- Harder: Streamdown's core is 508 kB, 155 kB compressed, past Vite's warning. The chat's route loads it, and no other; phase 7 sets the size budgets.
- Harder: a change to `client`'s store's shapes is a change to `ui`'s components.
