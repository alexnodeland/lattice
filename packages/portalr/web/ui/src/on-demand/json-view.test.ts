import { expect, test } from "vitest";
import { LONGEST, languageOf, parseJson } from "./json-view";

test("JSON parses as it is; what isn't JSON, or is empty, is nothing", () => {
  expect(parseJson('{"a": [1, "two", {"b": null}]}')).toEqual({
    value: { a: [1, "two", { b: null }] },
    repaired: false,
  });
  expect(parseJson('"a string"')).toEqual({ value: "a string", repaired: false });
  expect(parseJson("not JSON…")).toBeUndefined();
  expect(parseJson("")).toBeUndefined();
  expect(parseJson("   ")).toBeUndefined();
  expect(parseJson("not JSON…", true)).toBeUndefined();
});

test("a value cut short is closed where it stopped, or cut back to what parses", () => {
  const cut = (text: string) => parseJson(text, true);
  expect(cut('{"html": "<!doctype html>\\n<p>Hi')).toEqual({
    value: { html: "<!doctype html>\n<p>Hi" },
    repaired: true,
  });
  expect(cut('{"a": "b", "c": {"d": [1, 2')).toEqual({
    value: { a: "b", c: { d: [1, 2] } },
    repaired: true,
  });
  expect(cut('{"a": "b", "c":')).toEqual({ value: { a: "b" }, repaired: true });
  expect(cut('{"a": "b", "c')).toEqual({ value: { a: "b" }, repaired: true });
  expect(cut('{"a": "say \\"hi')).toEqual({ value: { a: 'say "hi' }, repaired: true });
  expect(cut('{"a": "ends in a backslash \\')).toEqual({
    value: { a: "ends in a backslash \\" },
    repaired: true,
  });
  expect(cut('{"a": "ünïcödé 😀')).toEqual({ value: { a: "ünïcödé 😀" }, repaired: true });
  expect(cut("[1, 2, 3")).toEqual({ value: [1, 2, 3], repaired: true });
  expect(cut("{")).toEqual({ value: {}, repaired: true });
  // A text that is whole isn't said to be repaired.
  expect(cut('{"a": 1}')).toEqual({ value: { a: 1 }, repaired: false });
});

test("a huge value is left raw, and a value just under the cap is formatted", () => {
  const huge = `{"html": "${"x".repeat(LONGEST)}"}`;
  expect(parseJson(huge)).toBeUndefined();
  expect(parseJson(huge, true)).toBeUndefined();
  const fits = `{"html": "${"x".repeat(LONGEST - 20)}"}`;
  expect(parseJson(fits)?.repaired).toBe(false);
  // A deep nest cut short is closed at every level; what can't be closed or cut back is nothing.
  expect(parseJson(`${"[".repeat(200)}1`, true)?.repaired).toBe(true);
  expect(parseJson("tru", true)).toBeUndefined();
});

test("a string's language is read from its key, then from its first characters", () => {
  expect(languageOf("html", "<p>")).toBe("html");
  expect(languageOf("body", "<!DOCTYPE html><html>")).toBe("html");
  expect(languageOf("style", "p { }")).toBe("css");
  expect(languageOf("script", "alert(1)")).toBe("javascript");
  expect(languageOf("source_ts", "let a")).toBe("typescript");
  expect(languageOf("code", "def main():")).toBe("python");
  expect(languageOf("query_sql", "select 1")).toBe("sql");
  expect(languageOf("markdown", "# Title")).toBe("markdown");
  expect(languageOf("source", "whatever")).toBe("");
  expect(languageOf("text", "Dear Alex,\nThanks.")).toBeNull();
});
