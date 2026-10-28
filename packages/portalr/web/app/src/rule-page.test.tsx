/**
 * A rule's page reads as a person reads a rule, When and Then first, with its JSON folded beneath
 * (portalr ADR-0085).
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

test("a rule says when it fires and what it does, in words, its JSON folded under them", async () => {
  const { screen } = await open("/t/acme/w/notes/rules/triage", serving({ triage: TRIAGE }));
  const term = (name: string) =>
    screen.getByText(name, { exact: true }).element().nextElementSibling;
  await expect.element(screen.getByText("portal:ticket.opened, each")).toBeVisible();
  expect(term("Then")?.textContent).toBe('triage {"to":"oncall"}');
  expect(term("For each")?.textContent).toBe("ticket");
  expect(term("Retries")?.textContent).toBe("up to 3 attempts");
  expect(term("Starts")?.textContent).toBe("from the log's beginning");
  expect(term("State")?.textContent).toBe("Disabled");
  const json = screen.getByRole("button", { name: "The rule, as reflexr's JSON" });
  await expect.element(json).toHaveAttribute("aria-expanded", "false");
  await json.click();
  await expect.element(screen.getByText(/"max_attempts": 3/)).toBeVisible();
});

test("a rule of another shape says its condition as JSON, and the defaults it leaves", async () => {
  const tidy = '{"name":"tidy","when":{"all":[]},"then":{"action":"notify"}}';
  const { screen } = await open("/t/acme/w/notes/rules/tidy", serving({ tidy }));
  await expect.element(screen.getByText('{"all":[]}')).toBeVisible();
  const term = (name: string) =>
    screen.getByText(name, { exact: true }).element().nextElementSibling;
  expect(term("Then")?.textContent).toBe("notify");
  expect(term("For each")?.textContent).toBe("the whole workspace");
  expect(term("Retries")?.textContent).toBe("up to 5 attempts");
  expect(term("Starts")?.textContent).toBe("from now on");
  expect(term("State")?.textContent).toBe("Enabled");
});
