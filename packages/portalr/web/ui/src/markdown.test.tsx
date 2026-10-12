import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { linkTo, Markdown, showable } from "./markdown";
import { token } from "./test/colours";

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
  const table = screen.container.querySelector("table");
  expect(table && style(table).borderTopColor).toBe(token("line"));
});

test("a caller's classes merge with the text's", async () => {
  const screen = await render(<Markdown className="text-muted">{"plain"}</Markdown>);
  const root = screen.getByText("plain").element().closest(".flex");
  expect(root?.classList).toContain("text-muted");
  expect(root?.classList).not.toContain("text-fg");
});
