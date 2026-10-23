/**
 * A native file's artifact page, over a stubbed server (portalr ADR-0048): its manifest, who has
 * it, its pages as images, a download, its words compared on demand, and, where its app is off in
 * the workspace, that it is only read here.
 */

import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { wordsChanged } from "./native";
import { holderOf } from "./native-file";
import { open } from "./test/app";
import { AT, FILE, FLAGS, PNG, REVISIONS, status } from "./test/files";

/** The server: the file's revisions, status, pages, words and bytes; grantr allows nothing more. */
function serving(
  lease: unknown = null,
  enabled = true,
  flags: Record<string, boolean> = {},
  pages = 2,
) {
  return async (_request: Request, path: string) => {
    switch (path) {
      case `${AT}/artifacts/doc_1/revisions`:
        return Response.json(REVISIONS);
      case FILE:
        return Response.json({ ...status(lease, enabled), pages });
      case FLAGS:
        return Response.json(flags);
      case "/grantr/v1/checks":
        return Response.json([false]);
      case `${FILE}/versions/2/pages/1`:
        return new Response(PNG);
      case `${FILE}/versions/1/text`:
        return new Response("Brief");
      case `${FILE}/versions/2/text`:
        return new Response("Brief\n\nFees");
      case `${FILE}/versions/2/content`:
        return new Response("the file's bytes");
      default:
        return undefined;
    }
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("a native file shows its manifest, who has it, and its pages", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", serving());
  await expect.element(screen.getByRole("heading", { name: "brief.docx" })).toBeVisible();
  await expect.element(screen.getByText("Word document · 48 kB · 2 pages")).toBeVisible();
  await expect
    .element(screen.getByRole("status").getByText("Available to check out"))
    .toBeVisible();
  const page = screen.getByRole("img", { name: "Page 1 of 2" });
  await expect.element(page).toBeVisible();
  expect(page.element().getAttribute("src")).toBe("data:image/png;base64,iVBORw0KGgo=");
  await expect.element(screen.getByText("This page couldn't be shown.")).toBeVisible();
});

test("a long file's pages are shown a few at a time", async () => {
  const { screen, fetched } = await open(
    "/t/acme/w/notes/artifacts/doc_1",
    serving(null, true, {}, 6),
  );
  const asked = () =>
    fetched.mock.calls
      .map(([input]) => new URL((input as Request).url).pathname)
      .filter((path) => path.includes("/pages/")).length;
  await expect.element(screen.getByText("Page 4 of 6")).toBeInTheDocument();
  expect(asked()).toBe(4);
  await screen.getByRole("button", { name: "Show more pages" }).click();
  await expect.element(screen.getByText("Page 6 of 6")).toBeInTheDocument();
  expect(asked()).toBe(6);
  expect(screen.getByRole("button", { name: "Show more pages" }).elements()).toHaveLength(0);
});

test("an agent's edit holding the file is said as one", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/artifacts/doc_1",
    serving({ checked_out_by: null, expires_at: "2026-10-17T09:31:00Z" }),
  );
  await expect
    .element(screen.getByRole("status").getByText("The agent is editing it"))
    .toBeVisible();
});

test("a status that can't be read says so, under the section's heading", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", async (request, path) =>
    path === FILE ? new Response("gone", { status: 400 }) : serving()(request, path),
  );
  await expect.element(screen.getByRole("heading", { name: "The file" })).toBeVisible();
  await expect.element(screen.getByText(/The file's status couldn't be read/)).toBeVisible();
});

test("a revision's words are compared when asked", async () => {
  const { screen, fetched } = await open("/t/acme/w/notes/artifacts/doc_1", serving());
  const asked = () =>
    fetched.mock.calls.filter(([input]) =>
      new URL((input as Request).url).pathname.endsWith("/text"),
    ).length;
  const disclosure = screen.getByText("Changes to its words");
  await expect.element(disclosure).toBeVisible();
  expect(asked()).toBe(0);
  await disclosure.click();
  await expect
    .poll(() => {
      // What this disclosure opens: the panel its button controls.
      const controls = disclosure
        .element()
        .closest("[aria-controls]")
        ?.getAttribute("aria-controls");
      return controls ? document.getElementById(controls)?.querySelector("ins")?.textContent : null;
    })
    .toBe("added: Fees");
  expect(asked()).toBe(2);
});

test("a download saves the version's bytes under the file's name", async () => {
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", serving());
  await screen.getByRole("button", { name: "Download" }).click();
  await expect.poll(() => clicked.mock.instances.length).toBe(1);
  const link = clicked.mock.instances[0] as unknown as HTMLAnchorElement;
  expect(link.download).toBe("brief.docx");
  expect(link.href.startsWith("blob:")).toBe(true);
});

test("a download that fails says so", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", async (request, path) =>
    path.endsWith("/content") ? new Response("gone", { status: 503 }) : serving()(request, path),
  );
  await screen.getByRole("button", { name: "Download" }).click();
  await expect
    .element(screen.getByText("The file wasn't downloaded. Try again in a moment."))
    .toBeVisible();
});

test.each([
  ["the server", false, {}],
  ["grantr", true, { "files:wordcraft": false }],
] as const)("off in the workspace, as %s says, it is only read", async (_by, enabled, flags) => {
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", serving(null, enabled, flags));
  await expect.element(screen.getByText(/WordCraft is off in this workspace/)).toBeVisible();
  expect(screen.getByText("Available to check out").elements()).toHaveLength(0);
  await expect.element(screen.getByRole("button", { name: "Download" })).toBeEnabled();
});

test("where native files' routes aren't served, the manifest is all there is", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", async (request, path) =>
    path === FILE
      ? Response.json({ detail: "Not Found" }, { status: 404 })
      : serving()(request, path),
  );
  await expect.element(screen.getByText("Word document · 48 kB · 2 pages")).toBeVisible();
  expect(screen.getByRole("button", { name: "Download" }).elements()).toHaveLength(0);
});

test("who has a file is the reader, a person by name, or the agent", () => {
  const names = (id: string) => `${id}@acme.test`;
  const until = "2026-10-17T17:30:00Z";
  expect(holderOf(null, "alice", names)).toEqual({ kind: "free" });
  expect(holderOf({ checked_out_by: null, expires_at: until }, "alice", names)).toEqual({
    kind: "agent",
  });
  expect(holderOf({ checked_out_by: "user:alice", expires_at: until }, "alice", names)).toEqual({
    kind: "you",
    until,
  });
  expect(holderOf({ checked_out_by: "user:bob", expires_at: until }, "alice", names)).toEqual({
    kind: "person",
    who: "bob@acme.test",
    until,
  });
  expect(
    holderOf({ checked_out_by: "external_agent:cli:1", expires_at: until }, "alice", names),
  ).toEqual({ kind: "person", who: "cli:1", until });
});

test("words change only between texts", () => {
  const text = (sha256: string | null) => ({ text: sha256 === null ? null : { sha256 } });
  expect(wordsChanged(text("a"), text("b"))).toBe(true);
  expect(wordsChanged(text("a"), text("a"))).toBe(false);
  expect(wordsChanged(text(null), text("b"))).toBe(false);
  expect(wordsChanged(text("a"), text(null))).toBe(false);
});

test("a download keeps the focus while it goes, says so politely, and is tried again only once", async () => {
  let asked = 0;
  let release: () => void = () => {};
  const held = new Promise<void>((done) => {
    release = done;
  });
  const { screen } = await open("/t/acme/w/notes/artifacts/doc_1", async (request, path) => {
    if (path.endsWith("/content")) {
      asked += 1;
      await held;
      return new Response("gone", { status: 503 });
    }
    return serving()(request, path);
  });
  const button = screen.getByRole("button", { name: "Download" });
  await expect.element(button).toBeVisible();
  (button.element() as HTMLElement).focus();
  await userEvent.keyboard("{Enter}");
  const going = screen.getByRole("button", { name: "Downloading…" });
  await expect.element(going).toHaveFocus();
  await expect.element(going).toHaveAttribute("aria-disabled", "true");
  // Pressed again while it goes, it starts nothing more.
  await userEvent.keyboard("{Enter}");
  await expect
    .element(screen.getByRole("status").filter({ hasText: "Downloading…" }))
    .toBeInTheDocument();
  release();
  await expect
    .element(screen.getByText("The file wasn't downloaded. Try again in a moment."))
    .toBeVisible();
  expect(asked).toBe(2);
  await expect.element(screen.getByRole("button", { name: "Download" })).toHaveFocus();
});
