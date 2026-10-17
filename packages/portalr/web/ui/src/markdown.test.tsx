import { expect, onTestFinished, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { AddonsProvider } from "./addons";
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
  expect(style(screen.getByRole("link", { name: "docs" }).element()).color).toBe(token("accent"));
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
  const wrap = screen.getByRole("button", { name: "Wrap" });
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
  await expect.element(screen.getByRole("status")).toHaveTextContent("Copied");
});

test("where there's no clipboard, Copy says it couldn't", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  onTestFinished(() => written.mockRestore());
  const screen = await render(<Markdown>{"```\nplain\n```"}</Markdown>);
  await screen.getByRole("button", { name: "Copy the code" }).click();
  await expect.element(screen.getByRole("status")).toHaveTextContent("Couldn't copy");
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
    <AddonsProvider value={{ mermaid: true }}>
      <Markdown>{fence}</Markdown>
    </AddonsProvider>,
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
    "svg:not(.lucide)",
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

test("streamed a character at a time, it never shows a half-written mark or a stray link", async () => {
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
