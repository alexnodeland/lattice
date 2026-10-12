import { expect, test } from "vitest";
import { authUrl } from "./deployment";
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

test("Supabase Auth is the project's, or at a path on this origin", () => {
  const origin = "https://app.example";
  expect(authUrl("https://project.supabase.co", origin)).toBe(
    "https://project.supabase.co/auth/v1",
  );
  expect(authUrl("https://project.supabase.co/", origin)).toBe(
    "https://project.supabase.co/auth/v1",
  );
  expect(authUrl("/", origin)).toBe("https://app.example/auth/v1");
});
