/**
 * What app shows where there is nothing at an address, or a read failed: the kit's states, which
 * take the focus where they stand in for the page, each with one way on (portalr ADR-0065).
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** grantr allowing everything, and `answer` for the rest. */
const serving =
  (answer: (path: string) => Response | undefined) => async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      const asked: unknown[] = await request.json();
      return Response.json(asked.map(() => true));
    }
    return (
      answer(path) ?? (path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined)
    );
  };

const missing = (part: string) =>
  serving((path) =>
    path.includes(part) ? Response.json({ detail: "not here" }, { status: 404 }) : undefined,
  );

test("an artifact that isn't there: its heading takes the focus, and the way on is all artifacts", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/art_missing", missing("art_missing"));
  const heading = screen.getByRole("heading", { name: "Artifact not found" });
  await expect.element(heading).toHaveFocus();
  await expect
    .element(screen.getByRole("link", { name: "All artifacts" }))
    .toHaveAttribute("href", "/t/acme/w/notes/artifacts");
});

test("a rule that isn't there: its heading takes the focus, and the way on is all rules", async () => {
  const { screen } = await open("/t/acme/w/notes/rules/rul_missing", missing("rul_missing"));
  await expect.element(screen.getByRole("heading", { name: "Rule not found" })).toHaveFocus();
  await expect.poll(() => document.title).toMatch(/^Rule not found · notes/);
  await expect
    .element(screen.getByRole("link", { name: "All rules" }))
    .toHaveAttribute("href", "/t/acme/w/notes/rules");
});

test("a read that fails outside the frame says what went wrong, and offers to start again", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/rules/rul_broken",
    serving((path) =>
      path.includes("rul_broken") ? new Response("down", { status: 500 }) : undefined,
    ),
  );
  await expect.element(screen.getByRole("heading", { name: "Something went wrong" })).toBeVisible();
  await expect
    .element(screen.getByRole("link", { name: "Start again" }))
    .toHaveAttribute("href", "/");
});

test("a tenant the reader isn't a member of is not found, named so, with a way to choose another", async () => {
  const { screen } = await open(
    "/t/nosuch",
    serving(() => undefined),
  );
  await expect
    .element(screen.getByRole("heading", { level: 1, name: "Tenant not found" }))
    .toBeVisible();
  expect(screen.getByRole("alert").elements()).toHaveLength(0);
  await expect.element(screen.getByRole("link", { name: "Choose a tenant" })).toBeVisible();
  await expect.poll(() => document.title).toMatch(/^Tenant not found · /);
  // A first load starts at the document, as a browser's does: the heading isn't focused.
  expect(document.activeElement).toBe(document.body);
});

test("an artifact that isn't there is the page's heading, in the window's title too", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/art_missing", missing("art_missing"));
  const heading = screen.getByRole("heading", { level: 1, name: "Artifact not found" });
  await expect.element(heading).toHaveFocus();
  await expect.poll(() => document.title).toMatch(/^Artifact not found · notes/);
});
