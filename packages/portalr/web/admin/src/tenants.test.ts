import { expect, test } from "vitest";
import { budgetSaid, isEmail, isTenantId, PAGE, rowsOf, spendSaid } from "./tenants";

const team = (
  tenant: string,
  spend: number,
  max: number | null = null,
  duration: string | null = null,
) => ({
  tenant,
  spend,
  max_budget: max,
  budget_duration: duration,
});

test("the tenants are by name, each with its team if it has one", () => {
  const rows = rowsOf(["globex", "acme", "initech"], {
    status: "ok",
    data: [team("acme", 12.5, 100, "30d"), team("stray", 1)],
  });
  expect(rows.map((row) => row.tenant)).toEqual(["acme", "globex", "initech"]);
  expect(rows[0]?.team?.spend).toBe(12.5);
  expect(rows[1]?.team).toBeNull();
});

test("a tenant's spend and budget are said as far as LiteLLM answered", () => {
  const [acme, globex, initech] = rowsOf(["acme", "globex", "initech"], {
    status: "ok",
    data: [team("acme", 25, 100, "30d"), team("initech", 3)],
  });
  expect(spendSaid(acme as never)).toBe("$25.00");
  expect(budgetSaid(acme as never, true)).toBe("$100.00 over 30 days, 25% spent");
  expect(spendSaid(globex as never)).toBe("–");
  expect(budgetSaid(globex as never, true)).toBe("No budget");
  expect(budgetSaid(initech as never, true)).toBe("No budget set");
  // LiteLLM didn't answer: nothing is said of any.
  expect(budgetSaid(acme as never, false)).toBe("–");
  const [none] = rowsOf(["acme"], { status: "unavailable", reason: "down" });
  expect(spendSaid(none as never)).toBe("–");
  expect(rowsOf(["a"], { status: "unconfigured" })[0]?.team).toBeNull();
});

test("a budget without a duration is said without one", () => {
  const [row] = rowsOf(["acme"], { status: "ok", data: [team("acme", 50, 100)] });
  expect(budgetSaid(row as never, true)).toBe("$100.00, 50% spent");
});

test("a page is fifty tenants", () => {
  expect(PAGE).toBe(50);
});

test("a tenant id is not empty and has no tilde; an email has an at and a dot and no spaces", () => {
  expect(["initech", "a b", "x.y"].every(isTenantId)).toBe(true);
  expect(["", "  ", "a~b"].some(isTenantId)).toBe(false);
  expect(isEmail("dan@initech.com")).toBe(true);
  expect(
    ["", "dan", "dan@x", "d an@x.com", "a@b@c.com", `${"x".repeat(250)}@y.com`].some(isEmail),
  ).toBe(false);
});
