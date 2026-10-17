# ADR-0042: Mermaid can't draw in the page under the policy, so it is parked

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

The chat's Markdown was to draw Mermaid's diagrams as inline SVG, with Mermaid's styles moved into constructable stylesheets, under the UIs' Content-Security-Policy as it is: `style-src 'self'`, with no `'unsafe-inline'`, no hash and no nonce ([ADR-0011](0011-the-router-and-its-readers.md)). The policy was not to be loosened; if a spike showed the approach couldn't be done cleanly, it was to be reported rather than built.

The spike built a page as app and admin are built, served it with the router's `policy()`, and drove it in Chromium through Playwright, recording every `securitypolicyviolation` event. It used Mermaid 12.2.0 and DOMPurify 3.4.17, with `securityLevel: "strict"`, `theme: "base"` and `suppressErrorRendering: true`, and drew eight kinds of diagram and two hostile ones.

## What the spike found

- **`mermaid.render()` breaks the policy as it lays a diagram out, before it returns anything.** It measures text in the live document: it inserts a `<style>` of its own, which is refused as `style-src-elem`, and sets `style` attributes through d3's `.attr("style")`, from 208 places in its code, which are refused as `style-src-attr`. Each kind of diagram broke it:

  | Diagram | `style-src-elem` | `style-src-attr` |
  |---|---|---|
  | flowchart | 2 | 44 |
  | sequence | 2 | 12 |
  | class | 2 | 57 |
  | state | 2 | 29 |
  | ER | 2 | 16 |
  | gantt | 2 | 13 |
  | pie | 2 | 6 |
  | mindmap | 3 | 28 |

- **So both ways of showing what it draws fail.** An image (`<img src="data:image/svg+xml,…">`, which `img-src` allows) and inline SVG with its styles moved into stylesheets each start from what `render()` returns, and `render()` has already broken the policy by then.
- **Chromium reports every `style` attribute that any HTML parse in the page meets,** whether through `DOMParser`, `createHTMLDocument` or a `<template>`, even in a document that never renders. Only writing styles through the CSS object model (`element.style`, a constructable stylesheet) is silent. Reworking Mermaid's SVG as a string afterwards can never reach zero, and DOMPurify, inside `render()`, parses the SVG again.
- **Styles applied afterwards draw the wrong shapes.** Mermaid sizes a diagram by its text as it is styled while it measures. With its styles held back until after `render()`, edge labels were clipped ("ye" for "yes") and node labels sat at the top of their boxes.
- **Zero violations takes patching the DOM itself.** For the length of each render, which is asynchronous, five of the browser's own members are replaced: `Element.prototype.setAttribute` and `setAttributeNS`, `Node.prototype.insertBefore` and `appendChild`, and the `innerHTML` getter. Each style becomes a rule in one constructable stylesheet, keyed by a `data-` attribute, and that sheet is adopted by the whole document while Mermaid measures. With that, all eight kinds and both hostile diagrams drew correctly with no style violation.
  - **What it costs:** every other library on the page runs against the replaced members while a render is in flight; two renders at once corrupt each other's restore, so it needs a lock; and it depends on how Mermaid 12.2.0 works inside, through its `setAttribute("style")` calls and its serializing through the enclosing element's `innerHTML`.
  - **What it still misses:** a hostile label (`<img src=x onerror=…>`) still raises one `script-src-attr` report, from DOMPurify's own parse, though nothing runs. A label's `<img src="x">` survives `strict` and requests a URL of this origin while Mermaid measures. `htmlLabels: false` stops that request, and shows `<b>` as text.
- **`securityLevel: "sandbox"` doesn't help.** It returns `<iframe src="data:text/html…">`, which the policy refuses (frames fall back to `default-src 'self'`), and it breaks the policy while drawing too.
- **It is large.** A first flowchart loads 30 chunks, 649 kB compressed, the largest 447 kB; all of Mermaid's chunks are 1,453 kB.

## Decision

- **Mermaid is parked.** A `mermaid` fence shows as its source, in `ui`'s code block, with one quiet line, through the add-ons seam that [ADR-0043](0043-markdowns-basics.md) adds, as an add-on that is switched off does. Nothing draws it.
- **No patch of the DOM is built, and the policy is not loosened.**
- **The spike's code is not kept.** This record holds what it found. Its page, server and driver are three short files, and the tests ADR-0043 adds hold the same policy, so a later attempt starts from those tests rather than from the spike.

## Options considered

| Option | For | Against |
|---|---|---|
| **A. Patch the DOM for each render, guarded** | Diagrams now; zero style violations in the spike | A patch of the browser's own members, racing with other renders and tied to Mermaid's internals; a hostile label is still reported |
| **B. Ask Mermaid for a rendering mode that writes styles through the CSS object model, and wait** | Clean, for everyone who runs a strict policy | Not ours to schedule |
| **C. Park it: show the source, with a quiet line (chosen)** | Nothing to keep in step; Markdown's basics, highlighting and math don't wait for it | No diagrams |
| D. A frame of its own with `style-src 'unsafe-inline'` | Mermaid as it is | Loosens the policy, on one route; ruled out |

## Consequences

- Easier: the Markdown's other add-ons go ahead without Mermaid, and none of them needs the policy to change.
- Harder: a model's diagram shows as text. The quiet line says why, and Copy takes the source to a viewer elsewhere.
- To revisit: when Mermaid can render through the CSS object model (B), or the owner accepts A with its guards. Either way, it must pass ADR-0043's tests under the policy, with no violation, before it ships.
