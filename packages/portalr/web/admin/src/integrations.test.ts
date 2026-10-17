import { expect, test } from "vitest";
import { levelOf, namedOf, rowsOf, settersOf, sourceOf } from "./integrations";

const ALICE = { on: true, by: { kind: "user", id: "alice" }, at: "2026-10-17T09:00:00Z" } as const;
const OFF = { ...ALICE, on: false };
const RULE = {
  on: false,
  by: { kind: "rule", rule: "ops:quiet", workspace: "notes" },
  at: ALICE.at,
} as const;

const state = (change: object = {}) => ({
  key: "markdown:mermaid",
  description: "Mermaid: diagrams written as text in messages, drawn.",
  default: false,
  installed: true,
  tenant: null,
  workspace: null,
  enabled: false,
  ...change,
});

test("the address names a workspace, or the tenant for none or anything grantr wouldn't take", () => {
  expect(levelOf({ workspace: "team/notes" })).toEqual({ workspace: "team/notes" });
  expect(levelOf({})).toEqual({ workspace: undefined });
  expect(levelOf({ workspace: "" })).toEqual({ workspace: undefined });
  expect(levelOf({ workspace: 42 })).toEqual({ workspace: undefined });
});

test("a state comes from a ceiling first, then this level, then the tenant, then the default", () => {
  expect(sourceOf(state({ installed: false, workspace: ALICE }), true)).toBe("not-installed");
  expect(sourceOf(state({ tenant: OFF, workspace: ALICE }), true)).toBe("tenant-off");
  expect(sourceOf(state({ tenant: ALICE, workspace: OFF }), true)).toBe("set");
  expect(sourceOf(state({ tenant: ALICE }), true)).toBe("inherited");
  expect(sourceOf(state(), true)).toBe("default");
  // On the tenant, its own off is a setting, not a ceiling, and nothing is inherited.
  expect(sourceOf(state({ tenant: OFF }), false)).toBe("set");
  expect(sourceOf(state({ workspace: ALICE }), false)).toBe("default");
});

test("an integration is named by its sentence's start, or by its key", () => {
  expect(namedOf(state())).toEqual({
    name: "Mermaid",
    description: "Diagrams written as text in messages, drawn.",
  });
  expect(namedOf(state({ key: "acme:x", description: "Without a name." }))).toEqual({
    name: "acme:x",
    description: "Without a name.",
  });
});

test("a row says who set it at its level, as people read them, and asks only for people", () => {
  const states = [state({ tenant: RULE, workspace: ALICE, enabled: true })];
  const names = (id: string) => (id === "alice" ? "alice@acme.test" : id);
  expect(rowsOf(states, true, names)).toEqual([
    {
      key: "markdown:mermaid",
      name: "Mermaid",
      description: "Diagrams written as text in messages, drawn.",
      on: true,
      source: "tenant-off",
      changed: { by: "alice@acme.test (person)", at: ALICE.at },
    },
  ]);
  expect(rowsOf(states, false, names)[0]?.changed?.by).toBe("ops:quiet (rule in notes)");
  expect(settersOf(states, true)).toEqual(["alice"]);
  expect(settersOf(states, false)).toEqual([]);
});
