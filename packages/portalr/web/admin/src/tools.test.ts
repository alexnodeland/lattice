import type { PortalrApi } from "@portalr/client";
import { expect, test } from "vitest";
import { asked, DOORS, NOTICE, safeHref, shownOf, tenantsOf } from "./tools";

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
  expect(shownOf({ tenant: 7 }).tenant).toBeUndefined();
});

test("links are asked for only once an id is given", () => {
  expect(asked(shownOf({}))).toBe(false);
  expect(asked(shownOf({ run: "r1" }))).toBe(true);
});

test("a link is an href only if it is an http or https address", () => {
  expect(safeHref("https://langfuse.example/project/p1/traces/t1")).toBe(
    "https://langfuse.example/project/p1/traces/t1",
  );
  expect(safeHref("http://localhost:3000/explore?left=%7B%7D")).toBe(
    "http://localhost:3000/explore?left=%7B%7D",
  );
  for (const bad of [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:x",
    "file:///etc/passwd",
    "//evil.example/x",
    "/relative/path",
    "not a url",
    "",
    null,
    undefined,
  ]) {
    expect(safeHref(bad), String(bad)).toBeNull();
  }
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
  ];
  expect([...fields].sort()).toEqual([...server].sort());
});

test("the notice says what the tools are outside of, and that opening them is recorded", () => {
  expect(NOTICE).toMatch(/aren't scoped to a tenant/);
  expect(NOTICE).toMatch(/outside the gates that Traces and Logs/);
  expect(NOTICE).toMatch(/is recorded/);
});

test("the tenants to ask for are by name, and none for someone who isn't an operator", () => {
  expect(tenantsOf({ tenants: ["b", "a"] })).toEqual(["a", "b"]);
  expect(tenantsOf(null)).toEqual([]);
});
