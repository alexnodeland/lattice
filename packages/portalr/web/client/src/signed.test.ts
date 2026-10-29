import { expect, test, vi } from "vitest";
import { authUrl, forgetDrafts } from "./signed";

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

/** A tab's session storage, as the browser keeps it: its items are its own keys. */
function tabStorage(items: Record<string, string>) {
  const storage = { ...items };
  Object.defineProperty(storage, "removeItem", {
    value: (key: string) => delete storage[key],
    enumerable: false,
  });
  return storage;
}

test("signing out lets go of every draft this tab keeps, and nothing else", () => {
  const storage = tabStorage({
    "portalr:draft:tn_1/us_1/th_1": "Half a thought",
    "portalr:draft:tn_2/us_1/tn_2/ws_1": "Another",
    "portalr:not-now:/portalr/app/": "kept",
  });
  vi.stubGlobal("sessionStorage", storage);
  forgetDrafts();
  vi.unstubAllGlobals();
  expect(Object.keys(storage)).toEqual(["portalr:not-now:/portalr/app/"]);
});

test("storage refused, signing out still goes on", () => {
  vi.stubGlobal("sessionStorage", undefined);
  expect(() => forgetDrafts()).not.toThrow();
  vi.unstubAllGlobals();
});
