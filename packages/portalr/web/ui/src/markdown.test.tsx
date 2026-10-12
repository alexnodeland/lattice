import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Markdown } from "./markdown";

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

test("raw HTML doesn't render: no script, no element", async () => {
  const screen = await render(
    <Markdown>{'Hi <script>window.pwned = true</script><b id="raw">raw</b>'}</Markdown>,
  );
  expect(screen.container.querySelector("script")).toBeNull();
  expect(screen.container.querySelector("#raw")).toBeNull();
  expect((window as { pwned?: boolean }).pwned).toBeUndefined();
});

test("a javascript: link doesn't render as a link", async () => {
  const screen = await render(<Markdown>{"[click](javascript:alert(1))"}</Markdown>);
  for (const link of screen.container.querySelectorAll("a")) {
    expect(link.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
  }
});

test("a link on the web opens apart from the app, telling it nothing", async () => {
  const screen = await render(<Markdown>{"[docs](https://example.com/docs)"}</Markdown>);
  const link = screen.getByRole("link", { name: "docs" }).element();
  expect(link.getAttribute("href")).toBe("https://example.com/docs");
  expect(link.getAttribute("rel")?.split(" ")).toEqual(
    expect.arrayContaining(["noopener", "noreferrer"]),
  );
});

test("an image from another origin is blocked; one from this origin shows", async () => {
  const screen = await render(
    <Markdown>{`![theirs](https://elsewhere.example/a.png)\n\n![ours](${location.origin}/b.png)`}</Markdown>,
  );
  const sources = [...screen.container.querySelectorAll("img")].map((image) => image.src);
  expect(sources).not.toContain("https://elsewhere.example/a.png");
  expect(sources).toContain(`${location.origin}/b.png`);
});

test("a caller's classes merge with the text's", async () => {
  const screen = await render(<Markdown className="text-muted">{"plain"}</Markdown>);
  const root = screen.getByText("plain").element().closest(".flex");
  expect(root?.classList).toContain("text-muted");
  expect(root?.classList).not.toContain("text-fg");
});
