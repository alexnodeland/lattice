import { expect, test } from "vitest";
import { authUrl } from "./deployment";

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
