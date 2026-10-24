import type { PortalrApi } from "@portalr/client";
import { expect, test } from "vitest";
import { asked, DOORS, ignoredOf, NOTICE, shownOf, TOOL_NAME, TOOLS, tenantsOf } from "./tools";

test("the address keeps the ids portalr takes and a tenant's name, and drops the rest", () => {
  expect(shownOf({})).toEqual({
    trace: undefined,
    session: undefined,
    run: undefined,
    tenant: undefined,
  });
  expect(shownOf({ trace: " t1 ", session: "thr_1", run: 42, tenant: "acme" })).toEqual({
    trace: "t1",
    session: "thr_1",
    run: "42",
    tenant: "acme",
  });
  expect(shownOf({ trace: "a b", session: "", run: "x".repeat(200), tenant: "a~b" })).toEqual({
    trace: undefined,
    session: undefined,
    run: undefined,
    tenant: undefined,
  });
  expect(shownOf({ tenant: "  " }).tenant).toBeUndefined();
  expect(shownOf({ tenant: " acme " }).tenant).toBe("acme");
  expect(shownOf({ tenant: 7 }).tenant).toBeUndefined();
});

test("links are asked for only once an id is given", () => {
  expect(asked(shownOf({}))).toBe(false);
  expect(asked(shownOf({ run: "r1" }))).toBe(true);
});

test("every link the server makes has a door, and each door is made by one kind of id", () => {
  const fields = new Set(DOORS.map((door) => door.field));
  const server: (keyof PortalrApi.components["schemas"]["Links"])[] = [
    "langfuse_trace",
    "langfuse_session",
    "langfuse_tenant",
    "grafana_trace",
    "grafana_logs",
    "grafana_tenant_logs",
    "grafana_tenant_traces",
    "umami_journeys",
  ];
  expect([...fields].sort()).toEqual([...server].sort());
});

test("the notice says what the tools are outside of, and that opening them is recorded", () => {
  expect(NOTICE).toMatch(/aren't scoped to a tenant/);
  expect(NOTICE).toMatch(/outside the gates that Traces and Logs/);
  expect(NOTICE).toMatch(/Links made here are recorded/);
  expect(NOTICE).toMatch(/A visit to any of them that doesn't start here/);
});

test("the tenants to ask for are by name, and none for someone who isn't an operator", () => {
  expect(tenantsOf({ tenants: ["b", "a"] })).toEqual(["a", "b"]);
  expect(tenantsOf(null)).toEqual([]);
});

test("what the address gave that isn't taken is named, and what is taken is not", () => {
  expect(
    ignoredOf({ trace: "not an id", session: "thr_1", run: "", tenant: "a~b", extra: "x" }),
  ).toEqual([
    { label: "Trace id", value: "not an id" },
    { label: "Tenant", value: "a~b" },
  ]);
  expect(ignoredOf({})).toEqual([]);
  expect(ignoredOf({ run: 7, tenant: " acme " })).toEqual([]);
  // What an address already says was ignored is kept, if it is well formed, and nothing else.
  expect(
    ignoredOf({
      trace: "t1",
      ignored: [
        { label: "Trace id", value: "x".repeat(200) },
        { label: "Nonsense", value: "y" },
        { label: "Run id", value: 7 },
        null,
      ],
    }),
  ).toEqual([{ label: "Trace id", value: "x".repeat(80) }]);
  expect(ignoredOf({ ignored: "not a list" })).toEqual([]);
});

test("each door's tool is one of the tools, which have names", () => {
  expect(DOORS.every((door) => TOOLS.includes(door.tool))).toBe(true);
  expect(TOOL_NAME).toEqual({ langfuse: "Langfuse", grafana: "Grafana", umami: "Umami" });
});
