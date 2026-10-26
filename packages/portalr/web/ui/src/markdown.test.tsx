import { expect, onTestFinished, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { IntegrationsContext } from "./integrations";
import { linkTo, Markdown, showable } from "./markdown";
import { axeViolations } from "./test/axe";
import { token } from "./test/colours";
import { GALLERY, HOSTILE } from "./test/markdown";

test("Markdown renders as the agent wrote it", async () => {
  const screen = await render(<Markdown>{"# Plan\n\n- **one**\n- two"}</Markdown>);
  await expect.element(screen.getByRole("heading", { name: "Plan" })).toBeVisible();
  await expect.element(screen.getByText("one")).toBeVisible();
  expect(screen.getByRole("listitem").elements()).toHaveLength(2);
});

test("unfinished Markdown is completed as it streams", async () => {
  const screen = await render(<Markdown streaming>{"Half **bold"}</Markdown>);
  await expect.element(screen.getByText("bold")).toBeVisible();
  expect(screen.container.textContent).not.toContain("**");
});

test("raw HTML shows as the text it is, never as elements", async () => {
  const screen = await render(
    <Markdown>
      {"Plain <b>bold</b> <script>alert(1)</script> <img src=x onerror=alert(1)>"}
    </Markdown>,
  );
  expect(screen.container.querySelector("b")).toBeNull();
  expect(screen.container.querySelector("script")).toBeNull();
  expect(screen.container.querySelector("img")).toBeNull();
  await expect.element(screen.getByText(/^Plain <b>bold<\/b>/)).toBeVisible();
});

test.each([
  "javascript:alert(1)",
  "JaVaScRiPt:alert(1)",
  "data:text/html,<b>x</b>",
  "vbscript:msgbox(1)",
  "xmpp:someone@example.com",
  "blob:https://example.com/x",
])("a link to %s is no link", async (href) => {
  const screen = await render(<Markdown>{`[click](${href})`}</Markdown>);
  await expect.element(screen.getByText("click")).toBeVisible();
  expect(screen.container.querySelector("a")).toBeNull();
});

test("a link on the web, written out or autolinked, opens apart from the app, telling it nothing", async () => {
  const screen = await render(
    <Markdown>{"[docs](https://example.com/docs) and <https://example.com/plain>"}</Markdown>,
  );
  for (const name of ["docs", "https://example.com/plain"]) {
    const link = screen.getByRole("link", { name }).element();
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  }
});

test("a link to a place on the page, or in the app, stays in the app", async () => {
  const screen = await render(<Markdown>{"[top](#top) and [plans](/portalr/app/)"}</Markdown>);
  for (const name of ["top", "plans"]) {
    const link = screen.getByRole("link", { name }).element();
    expect(link.getAttribute("target")).toBeNull();
  }
});

test("where a link may go, and an image show from", () => {
  const origin = "https://app.example";
  expect(linkTo("mailto:team@example.com", origin)).toEqual({
    href: "mailto:team@example.com",
    away: true,
  });
  expect(linkTo("/portalr/app/", origin)).toEqual({
    href: "https://app.example/portalr/app/",
    away: false,
  });
  expect(linkTo(undefined, origin)).toBeNull();
  expect(linkTo("https://[bad", origin)).toBeNull();
  expect(showable("/a.png", origin)).toBe("https://app.example/a.png");
  expect(showable("https://elsewhere.example/a.png", origin)).toBeNull();
  expect(showable("https://[bad", origin)).toBeNull();
  expect(showable(undefined, origin)).toBeNull();
});

test("an image from another origin is blocked, saying so; one from this origin shows", async () => {
  const screen = await render(
    <Markdown>{`![theirs](https://elsewhere.example/a.png)\n\n![ours](${location.origin}/b.png)`}</Markdown>,
  );
  const sources = [...screen.container.querySelectorAll("img")].map((image) => image.src);
  expect(sources).toEqual([`${location.origin}/b.png`]);
  await expect.element(screen.getByText("Image blocked: theirs")).toBeVisible();
});

test("its links, code, quotes and tables take portalr's colours", async () => {
  const screen = await render(
    <Markdown>{"[docs](https://example.com) `code`\n\n> quoted\n\n| a |\n|---|\n| b |"}</Markdown>,
  );
  const style = (element: Element) => getComputedStyle(element);
  const link = screen.getByRole("link", { name: "docs" }).element();
  expect(style(link).color).toBe(token("accent"));
  // A message's link is the kit's inline link: reached by the keyboard, it has the kit's ring.
  link.focus();
  await userEvent.keyboard("{Shift}");
  expect(style(link).outlineColor).toBe(token("focus"));
  const code = screen.getByText("code").element();
  expect(style(code).backgroundColor).toBe(token("paper"));
  expect(style(code).color).toBe(token("fg"));
  const quote = screen.container.querySelector("blockquote");
  expect(quote && style(quote).color).toBe(token("muted"));
  const table = screen.getByRole("region", { name: "Table" }).element();
  expect(style(table).borderTopColor).toBe(token("line"));
});

test("a caller's classes merge with the text's", async () => {
  const screen = await render(<Markdown className="text-muted">{"plain"}</Markdown>);
  const root = screen.getByText("plain").element().closest(".flex");
  expect(root?.classList).toContain("text-muted");
  expect(root?.classList).not.toContain("text-fg");
});

test("a link still streaming is no link until it is whole", async () => {
  const screen = await render(
    <Markdown streaming>{"See [the docs](https://example.com/do"}</Markdown>,
  );
  await expect.element(screen.getByText("the docs")).toBeVisible();
  expect(screen.container.querySelector("a")).toBeNull();
  expect(screen.container.innerHTML).not.toContain("streamdown:");
});

test("a `$$` mid-stream stays as it was written: no math is drawn, so none is closed", async () => {
  const screen = await render(<Markdown streaming>{"Costs $$x + y"}</Markdown>);
  await expect.element(screen.getByText("Costs $$x + y", { exact: true })).toBeVisible();
});

test("each Markdown's footnotes are its own: two messages' first footnotes never share an id", async () => {
  const text = "Said.[^1]\n\n[^1]: Because.";
  const screen = await render(
    <>
      <Markdown>{text}</Markdown>
      <Markdown>{text}</Markdown>
    </>,
  );
  const references = [...screen.container.querySelectorAll("sup > a")];
  expect(references).toHaveLength(2);
  const targets = references.map((reference) => reference.getAttribute("href") ?? "");
  expect(new Set(targets).size).toBe(2);
  for (const target of targets) {
    expect(screen.container.querySelectorAll(`[id="${target.slice(1)}"]`)).toHaveLength(1);
  }
});

test("a fenced block names its language, scrolls in a region a keyboard reaches, and wraps on asking", async () => {
  const screen = await render(<Markdown>{"```ts\nconst answer = 42;\n```"}</Markdown>);
  await expect.element(screen.getByText("ts", { exact: true })).toBeVisible();
  const region = screen.getByRole("region", { name: "ts code" });
  expect(region.element().tabIndex).toBe(0);
  const pre = region.element().querySelector("pre") as Element;
  expect(getComputedStyle(pre).whiteSpace).toBe("pre");
  const wrap = screen.getByRole("button", { name: "Wrap the ts code" });
  await wrap.click();
  await expect.element(wrap).toHaveAttribute("aria-pressed", "true");
  expect(getComputedStyle(pre).whiteSpace).toBe("pre-wrap");
});

test("Copy copies a block's code as it was written, and says so politely", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => written.mockRestore());
  const screen = await render(<Markdown>{"```py\nprint('<b>hi</b>')\n```"}</Markdown>);
  await screen.getByRole("button", { name: "Copy the py code" }).click();
  expect(written).toHaveBeenCalledWith("print('<b>hi</b>')");
  await expect.element(screen.getByRole("button", { name: "Copied the py code" })).toBeVisible();
  await expect.element(screen.getByRole("status")).toHaveTextContent("Copied the py code");
});

test("where there's no clipboard, Copy says it couldn't", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  onTestFinished(() => written.mockRestore());
  const screen = await render(<Markdown>{"```\nplain\n```"}</Markdown>);
  await screen.getByRole("button", { name: "Copy the code" }).click();
  await expect.element(screen.getByRole("status")).toHaveTextContent("Couldn't copy the code");
  await expect.element(screen.getByRole("region", { name: "Code" })).toHaveTextContent("plain");
});

test("a diagram shows as its source with one quiet line, whether diagrams are off or on", async () => {
  const fence = "```mermaid\nflowchart LR\n  A --> B\n```";
  const off = await render(<Markdown>{fence}</Markdown>);
  await expect
    .element(off.getByRole("region", { name: "mermaid code" }))
    .toHaveTextContent("flowchart LR A --> B");
  await expect
    .element(off.getByText("Diagrams are off here: this is the diagram's source."))
    .toBeVisible();
  expect(off.container.querySelector("svg:not([aria-hidden=true])")).toBeNull();
  const on = await render(
    <IntegrationsContext value={() => true}>
      <Markdown>{fence}</Markdown>
    </IntegrationsContext>,
  );
  await expect
    .element(on.getByText("Diagrams can't be drawn yet: this is the diagram's source."))
    .toBeVisible();
});

test.each([
  ["NOTE", "Note"],
  ["tip", "Tip"],
  ["Important", "Important"],
  ["WARNING", "Warning"],
  ["CAUTION", "Caution"],
])(
  "a [!%s] quote is a callout, a note with its word, never a live region",
  async (marker, word) => {
    const screen = await render(<Markdown>{`> [!${marker}]\n> Read **this**.`}</Markdown>);
    const note = screen.getByRole("note");
    await expect.element(note).toHaveTextContent(`${word} Read this.`);
    expect(screen.container.textContent).not.toContain("[!");
    expect(screen.container.querySelector("blockquote, [role=alert], [role=status]")).toBeNull();
  },
);

test("a callout's tone is its edge: a warning gold, a caution red", async () => {
  const screen = await render(
    <Markdown>{"> [!WARNING]\n> Careful.\n\n> [!CAUTION]\n> Stop."}</Markdown>,
  );
  const [warning, caution] = screen.getByRole("note").elements();
  expect(warning && getComputedStyle(warning).borderLeftColor).toBe(token("status-warn"));
  expect(caution && getComputedStyle(caution).borderLeftColor).toBe(token("status-failed"));
});

test("a quote that isn't a callout stays a quote: an unknown kind, or a marker not on its first line", async () => {
  const screen = await render(
    <Markdown>{"> [!DANGER]\n> Not a kind.\n\n> First line.\n> [!NOTE] too late"}</Markdown>,
  );
  expect(screen.container.querySelectorAll("blockquote")).toHaveLength(2);
  expect(screen.container.querySelector("[role=note]")).toBeNull();
});

test("a callout holds whatever a quote can, and a quote holds callouts too", async () => {
  const screen = await render(
    <Markdown>{"> [!TIP]\n>\n> - one\n> - two\n\n- item\n\n  > [!NOTE]\n  > Nested."}</Markdown>,
  );
  const [tip, nested] = screen.getByRole("note").elements();
  expect(tip?.querySelectorAll("li")).toHaveLength(2);
  expect(nested?.textContent).toMatch(/^Note\s*Nested\.\s*$/);
});

test.each(HOSTILE)("hostile Markdown runs, loads and links nothing: %s", async (text) => {
  const screen = await render(<Markdown>{text}</Markdown>);
  // An icon is the one drawing: hidden from assistive technology, and ui's own.
  for (const element of [
    "script",
    "iframe",
    "style",
    "img",
    "svg:not([data-glyph])",
    "[style], [onerror]",
  ]) {
    expect(screen.container.querySelector(element)).toBeNull();
  }
  for (const link of screen.container.querySelectorAll("[href]")) {
    expect(link.getAttribute("href")).not.toMatch(/^(?:javascript|data|vbscript):/i);
  }
});

test("a task list's boxes say done or to do in words, and are drawings, never controls", async () => {
  const screen = await render(<Markdown>{"- [x] Tests pass\n- [ ] Docs updated"}</Markdown>);
  const items = screen.getByRole("listitem").elements();
  expect(items.map((item) => item.textContent?.trim())).toEqual([
    "Done: Tests pass",
    "To do: Docs updated",
  ]);
  expect(screen.container.querySelector("input")).toBeNull();
});

test("every element, together, has nothing axe finds wrong", async () => {
  const screen = await render(<Markdown>{GALLERY}</Markdown>);
  await expect.element(screen.getByRole("heading", { name: "The launch plan" })).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
});

// About 1,400 renders, each awaited: the time is the renders', not a wait. They took a loaded CI
// runner 48 s of a 60 s budget, so the budget is a backstop five times that: a render that never
// finishes still fails, one slow runner doesn't.
test("streamed a character at a time, it never shows a half-written mark or a stray link", {
  timeout: 300_000,
}, async () => {
  const screen = await render(<Markdown streaming>{""}</Markdown>);
  for (let end = 1; end <= GALLERY.length; end += 1) {
    await screen.rerender(<Markdown streaming>{GALLERY.slice(0, end)}</Markdown>);
    const shown = screen.container.textContent ?? "";
    // A mark with nothing after it yet shows for a moment; one with words after it is closed.
    expect(shown, `at ${end}`).not.toMatch(/\*\*\w|~~\w/);
    expect(screen.container.querySelector('a[href^="streamdown:"]'), `at ${end}`).toBeNull();
  }
  await screen.rerender(<Markdown>{GALLERY}</Markdown>);
  await expect.element(screen.getByRole("note").first()).toBeVisible();
});

test("a block in a language ui highlights is drawn in code's colours, which tokens.css sets", async () => {
  const screen = await render(
    <Markdown>{"```ts\nconst answer: number = 42; // why\n```"}</Markdown>,
  );
  const region = screen.getByRole("region", { name: "ts code" }).element();
  await expect.poll(() => region.querySelectorAll("span").length).toBeGreaterThan(3);
  const keyword = [...region.querySelectorAll("span")].find((span) => span.textContent === "const");
  expect(keyword && getComputedStyle(keyword).color).toBe(token("code-token-keyword"));
  const comment = [...region.querySelectorAll("span")].find((span) =>
    span.textContent?.includes("why"),
  );
  expect(comment && getComputedStyle(comment).fontStyle).toBe("italic");
  expect(comment && getComputedStyle(comment).color).toBe(token("code-token-comment"));
  expect(region.textContent).toBe("const answer: number = 42; // why");
});

test("a block in a language ui doesn't highlight, or in none, is shown as it is", async () => {
  const screen = await render(
    <Markdown>{"```brainfuck\n+[-->-[>>+>-----<<]<--<---]>-.\n```"}</Markdown>,
  );
  const region = screen.getByRole("region", { name: "brainfuck code" }).element();
  // No grammar loads for it, so what shows first is what stays.
  expect(region.querySelector("span")).toBeNull();
});

test("a block still streaming is highlighted a whole line at a time; the line arriving is as it is", async () => {
  const screen = await render(<Markdown streaming>{"```py\ndef f():\n    retu"}</Markdown>);
  const region = screen.getByRole("region", { name: "py code" }).element();
  await expect.poll(() => region.querySelectorAll("span").length).toBeGreaterThan(1);
  const spans = [...region.querySelectorAll("span")].map((span) => span.textContent).join("");
  expect(spans).toBe("def f():");
  expect(region.textContent).toBe("def f():\n    retu");
  await screen.rerender(<Markdown streaming>{"```py\ndef f():\n    return 1\n```"}</Markdown>);
  await expect
    .poll(() => [...region.querySelectorAll("span")].map((span) => span.textContent).join(""))
    .toBe("def f():    return 1");
});

test("math, within a line or on lines of its own, is drawn as MathML", async () => {
  const screen = await render(
    <Markdown>
      {"Energy is $$E = mc^2$$ here.\n\n$$\n\\frac{a}{b}\n$$\n\n```math\nx^2\n```"}
    </Markdown>,
  );
  await expect.poll(() => screen.container.querySelectorAll("math").length).toBe(3);
  const [inline, block, fenced] = [...screen.container.querySelectorAll("math")];
  expect(inline?.getAttribute("display")).toBeNull();
  expect(block?.getAttribute("display")).toBe("block");
  expect(fenced?.getAttribute("display")).toBe("block");
  await expect.element(screen.getByRole("region", { name: "Formula" }).first()).toBeVisible();
  expect(screen.container.textContent).not.toContain("$$");
});

test("a single dollar is a price, never math", async () => {
  const screen = await render(<Markdown>{"It costs $5, or $10 with $$x$$"}</Markdown>);
  await expect.poll(() => screen.container.querySelectorAll("math").length).toBe(1);
  expect(screen.container.querySelector("math")?.textContent).toContain("x");
  await expect.element(screen.getByText(/It costs \$5, or \$10/)).toBeVisible();
});

test("with math off, a formula is its source: a block with its quiet line, and $$ within a line", async () => {
  const screen = await render(
    <IntegrationsContext value={(key) => key !== "markdown:math" && key !== "markdown:mermaid"}>
      <Markdown>{"Energy is $$E = mc^2$$.\n\n$$\n\\frac{a}{b}\n$$"}</Markdown>
    </IntegrationsContext>,
  );
  await expect
    .element(screen.getByText("Math is off here: this is the formula's source."))
    .toBeVisible();
  await expect
    .element(screen.getByRole("region", { name: "math code" }))
    .toHaveTextContent("\\frac{a}{b}");
  await expect.element(screen.getByText("$$E = mc^2$$")).toBeVisible();
  expect(screen.container.querySelector("math")).toBeNull();
});

test("TeX that isn't a formula is its source, with a quiet line, once it has all arrived", async () => {
  const text = "$$\n\\frac{a}{\n$$";
  // The formula beside it shows math has loaded; still streaming, no line says this one failed.
  const streaming = await render(<Markdown streaming>{`$$x$$\n\n${text}`}</Markdown>);
  await expect.poll(() => streaming.container.querySelectorAll("math").length).toBe(1);
  expect(streaming.container.textContent).not.toContain("couldn't be drawn");
  const screen = await render(<Markdown>{text}</Markdown>);
  await expect
    .element(screen.getByText("This formula couldn't be drawn: this is its source."))
    .toBeVisible();
});

test.each([
  "\\href{javascript:alert(1)}{click}",
  "\\url{javascript:alert(1)}",
  "\\htmlStyle{color:red}{x}",
  "\\htmlClass{x}{y}",
  "\\includegraphics{https://tracker.example/x.png}",
  "\\fcolorbox{red}{blue}{x}",
  "\\pmb{x}",
])("hostile TeX is drawn as math that links, loads and styles nothing: %s", async (tex) => {
  const screen = await render(<Markdown>{`$$\n${tex}\n$$`}</Markdown>);
  await expect.poll(() => screen.container.querySelector("math")).not.toBeNull();
  expect(screen.container.querySelector("[href], img, [style], script")).toBeNull();
});

test("TeX that expands without end is refused, and shown as its source", async () => {
  const screen = await render(<Markdown>{"$$\n\\def\\x{\\x}\\x\n$$"}</Markdown>);
  await expect
    .element(screen.getByText("This formula couldn't be drawn: this is its source."))
    .toBeVisible();
  expect(screen.container.querySelector("math")).toBeNull();
});

test("an svg a message writes with the kit's own mark on it is still no drawing", async () => {
  const screen = await render(
    <Markdown>{'<svg data-glyph=""><path d="M0 0h16v16z"/></svg> words'}</Markdown>,
  );
  expect(screen.container.querySelector("svg")).toBeNull();
  await expect.element(screen.getByText(/words/)).toBeVisible();
});
