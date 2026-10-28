/**
 * A rule's page reads as a person reads a rule, the pipeline it runs, stage by stage, with its JSON
 * folded beneath, or, for a stored rule one may change, in the field that edits it (portalr
 * ADR-0017, ADR-0085).
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** grantr allowing nothing to change, and the rules each test names. */
const serving = (rules: Record<string, string>) => async (request: Request, path: string) => {
  if (path === "/grantr/v1/checks") {
    const asked: unknown[] = await request.json();
    return Response.json(asked.map(() => false));
  }
  const name = Object.keys(rules).find((rule) => path.endsWith(`/rules/${rule}`));
  if (name !== undefined) {
    // As text: a rule's `then` is its action, which an object literal can't name safely.
    return new Response(`{"origin":"code","version":null,"rule":${rules[name]}}`, {
      headers: { "content-type": "application/json" },
    });
  }
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

const TRIAGE =
  '{"name":"triage","description":"Sort a ticket.","when":{"filter":{"kind":"on","types":["portal:ticket.opened"]},"pattern":{"kind":"each"}},"scope":{"fields":["ticket"]},"then":{"action":"triage","params":{"to":"oncall"}},"retry":{"max_attempts":3},"start":"beginning","enabled":false}';

/** What a stage of the rule's pipeline says. */
const stage = (screen: Awaited<ReturnType<typeof open>>["screen"], name: string) =>
  screen
    .getByRole("list", { name: "The rule, stage by stage" })
    .getByText(name, { exact: true })
    .element().nextElementSibling?.textContent;

test("a code rule is shown as its pipeline, its JSON folded under it", async () => {
  const { screen } = await open("/t/acme/w/notes/rules/triage", serving({ triage: TRIAGE }));
  await expect.element(screen.getByText("portal:ticket.opened", { exact: true })).toBeVisible();
  expect(stage(screen, "event types")).toBe("portal:ticket.opened");
  expect(stage(screen, "pattern")).toBe("each event");
  expect(stage(screen, "scope")).toBe("per ticket");
  expect(stage(screen, "action")).toBe('triageto: "oncall"');
  expect(stage(screen, "retries")).toMatch(/^up to 3 attempts/);
  expect(stage(screen, "more")).toBe('start: "beginning"');
  await expect.element(screen.getByText("Disabled", { exact: true })).toBeVisible();
  const json = screen.getByRole("button", { name: "The rule, as reflexr's JSON" });
  await expect.element(json).toHaveAttribute("aria-expanded", "false");
  await json.click();
  await expect.element(screen.getByText(/"max_attempts": 3/)).toBeVisible();
});

test("a rule of another shape shows that part as JSON, in its place, and the defaults it leaves", async () => {
  const tidy = '{"name":"tidy","when":{"all":[]},"then":{"action":"notify"}}';
  const { screen } = await open("/t/acme/w/notes/rules/tidy", serving({ tidy }));
  await expect.element(screen.getByText("when.all: []")).toBeVisible();
  expect(stage(screen, "action")).toBe("notify");
  expect(stage(screen, "scope")).toBe("one scope");
  expect(stage(screen, "retries")).toMatch(/^up to 5 attempts/);
  expect(stage(screen, "more")).toBe("when.all: []");
  await expect.element(screen.getByText("Enabled", { exact: true })).toBeVisible();
});

test("a stored rule shows its pipeline above the field that edits its JSON", async () => {
  const stored = async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      const asked: unknown[] = await request.json();
      return Response.json(asked.map(() => true));
    }
    if (path.endsWith("/rules/triage")) {
      return new Response(`{"origin":"stored","version":2,"rule":${TRIAGE}}`, {
        headers: { "content-type": "application/json" },
      });
    }
    return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
  };
  const { screen } = await open("/t/acme/w/notes/rules/triage", stored);
  await expect.element(screen.getByText("per ticket")).toBeVisible();
  const field = screen.getByRole("textbox", { name: "Rule, as reflexr's JSON" });
  await expect.element(field).toBeVisible();
  const pipeline = screen.getByRole("list", { name: "The rule, stage by stage" }).element();
  expect(
    pipeline.compareDocumentPosition(field.element()) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});
