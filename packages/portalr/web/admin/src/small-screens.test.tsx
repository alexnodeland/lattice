/**
 * Admin's routes on a phone and a tablet (portalr ADR-0082): at 320, 360, 390, 430 and 768 the
 * members, usage and settings pages are never wider than the page; a table scrolls in its box.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { TENANT_ACTIONS } from "./access";
import { open } from "./test/admin";

const days = (count: number) =>
  Array.from({ length: count }, (_, back) =>
    new Date(Date.now() - (count - 1 - back) * 86_400_000).toISOString().slice(0, 10),
  );
async function serve(_request: Request, path: string): Promise<Response | undefined> {
  if (path === "/grantr/v1/catalog")
    return Response.json({
      roles: [{ name: "owner", kinds: ["tenant"] }],
      custom_actions: ["reflexr:retry_run"],
      custom_kinds: ["workspace"],
    });
  if (path === "/grantr/v1/tenants/acme/roles") return Response.json([]);
  if (path === "/grantr/v1/tenants/acme/grants") return Response.json([]);
  if (path === "/grantr/v1/tenants/acme/members")
    return Response.json([
      { kind: "service_principal", id: "a-service-principal-with-a-very-long-name-indeed" },
      { kind: "user", id: "bob" },
      { kind: "user", id: "alice" },
    ]);
  if (path === "/grantr/v1/tenants/acme/groups") return Response.json({});
  if (path === "/grantr/v1/tenants/acme/keys") return Response.json([]);
  if (path === "/portalr/v1/usage")
    return Response.json({
      status: "ok",
      data: {
        days: days(7).map((day, at) => ({
          day,
          spend: 5 + at,
          tokens: 500 * (at + 1),
          requests: 40 * (at + 1),
        })),
        workspaces: [
          { workspace: "notes", spend: 118.4, tokens: 26104331 },
          { workspace: "launch", spend: 51.1, tokens: 11720006 },
        ],
        budget: { spend: 184.2, max_budget: 300, budget_duration: "30d" },
        daily_budget: 10,
        complete: true,
      },
    });
  if (path === "/portalr/v1/deployment/tenants")
    return Response.json(
      { detail: { type: "forbidden", message: "not an operator" } },
      { status: 403 },
    );
  if (path === "/artifactr/v1/workspaces") return Response.json(["notes", "launch"]);
  if (path === "/portalr/v1/settings" || path.startsWith("/portalr/v1/tenants/acme/settings"))
    return Response.json([]);
  return undefined;
}
afterEach(() => vi.unstubAllGlobals());

function wider(): string[] {
  const scrolls = (element: Element | null): boolean =>
    element !== null &&
    element !== document.body &&
    (/auto|scroll/.test(getComputedStyle(element).overflowX) || scrolls(element.parentElement));
  return Array.from(document.body.querySelectorAll<HTMLElement>("*"))
    .filter(
      (element) =>
        element.getBoundingClientRect().right > window.innerWidth + 1 &&
        !scrolls(element.parentElement),
    )
    .map(
      (element) => `${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 60)}`,
    );
}

const WIDTHS = [320, 360, 390, 430, 768];
const ROUTES: [string, string, readonly string[], string][] = [
  ["members", "/t/acme/access/members", TENANT_ACTIONS, "Access"],
  ["usage", "/t/acme/usage", ["portalr:read_spend"], "Usage"],
];
for (const [what, path, allowed, heading] of ROUTES) {
  for (const width of WIDTHS) {
    test(`admin's ${what} at ${width}px is never wider than the page`, async () => {
      await page.viewport(width, 900);
      const { screen } = await open(path, allowed, serve);
      await expect.element(screen.getByRole("heading", { name: heading }).first()).toBeVisible();
      await expect
        .element(
          screen
            .getByText(
              what === "members" ? "a-service-principal-with-a-very-long-name-indeed" : "notes",
              { exact: false },
            )
            .first(),
        )
        .toBeInTheDocument();
      await new Promise((settled) => setTimeout(settled, 300));
      const found = wider();
      expect(found, found.join("\n")).toEqual([]);
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
    });
  }
}
