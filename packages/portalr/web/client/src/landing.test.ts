import { expect, test } from "vitest";
import { administered, adminLanding, landing } from "./landing";

const member = (tenant: string) => ({ tenant });

test("a person in no tenant has no access, not an empty app", () => {
  expect(landing([])).toEqual({ kind: "no-access" });
});

test("a person in one tenant never sees the picker", () => {
  expect(landing([member("acme")])).toEqual({ kind: "tenant", tenant: "acme" });
});

test("a person in several picks one, in order", () => {
  expect(landing([member("globex"), member("acme")])).toEqual({
    kind: "choose",
    tenants: ["acme", "globex"],
  });
});

const holds = (tenant: string, ...roles: string[]) => ({ tenant, roles });

test("admin offers the tenants someone owns or administers, and not those they're only in", () => {
  expect(
    administered([holds("globex", "admin"), holds("acme", "owner"), holds("initech")]),
  ).toEqual(["acme", "globex"]);
});

test("admin opens on someone's one tenant, every tenant for an operator, or no access", () => {
  expect(adminLanding([holds("acme", "owner")], false, null)).toEqual({
    kind: "tenant",
    tenant: "acme",
  });
  expect(adminLanding([holds("acme", "member")], true, null)).toEqual({ kind: "deployment" });
  expect(adminLanding([holds("acme", "member")], false, null)).toEqual({ kind: "no-access" });
  expect(adminLanding([holds("acme", "owner")], true, null)).toEqual({
    kind: "choose",
    tenants: ["acme"],
    operator: true,
  });
});

test("admin's last choice comes first while it is still theirs", () => {
  const two = [holds("acme", "owner"), holds("globex", "admin")];
  expect(adminLanding(two, false, "globex")).toEqual({ kind: "tenant", tenant: "globex" });
  expect(adminLanding(two, true, "deployment")).toEqual({ kind: "deployment" });
  expect(adminLanding(two, false, "deployment")).toEqual({
    kind: "choose",
    tenants: ["acme", "globex"],
    operator: false,
  });
  expect(adminLanding(two, false, "initech")).toMatchObject({ kind: "choose" });
});
