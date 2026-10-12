import { expect, test } from "vitest";
import { landing } from "./landing";

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
