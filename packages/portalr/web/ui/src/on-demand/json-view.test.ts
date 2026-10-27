import { expect, test } from "vitest";
import { LONGEST, languageOf, MOST, parseJson, tooHeavy } from "./json-view";

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
  // A number cut at the end can't be known: it goes.
  expect(cut('{"a": "b", "c": {"d": [1, 2')).toEqual({
    value: { a: "b", c: { d: [1] } },
    repaired: true,
  });
  expect(cut('{"a": 12')).toEqual({ value: {}, repaired: true });
  expect(cut('{"a": 12, "b": 3')).toEqual({ value: { a: 12 }, repaired: true });
  expect(cut('{"a": "x, y", "b": tru')).toEqual({ value: { a: "x, y" }, repaired: true });
  // A comma inside a string is never where it is cut back to.
  expect(cut('{"a": "x,')).toEqual({ value: { a: "x," }, repaired: true });
  expect(cut('{"a": "x, y", "b": {"c": "d, e')).toEqual({
    value: { a: "x, y", b: { c: "d, e" } },
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
  expect(cut("[1, 2, 3")).toEqual({ value: [1, 2], repaired: true });
  expect(cut("[1, 2, 3]")).toEqual({ value: [1, 2, 3], repaired: false });
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
  // A nest a hundred thousand deep, or a hundred thousand values, is too heavy to lay out.
  const deep = "[".repeat(100_000);
  expect(parseJson(deep)).toBeUndefined();
  const parsedDeep = parseJson(deep, true);
  expect(parsedDeep === undefined || tooHeavy(parsedDeep.value)).toBe(true);
  const wide = parseJson(`[${Array.from({ length: 90_000 }, () => "1").join(",")}]`);
  expect(wide?.repaired).toBe(false);
  expect(tooHeavy(wide?.value)).toBe(true);
  expect(tooHeavy(Array.from({ length: 100_000 }, () => 1))).toBe(true);
  expect(tooHeavy(Array.from({ length: MOST - 1 }, () => 1))).toBe(false);
  expect(tooHeavy({ a: { b: { c: [1, { d: "e" }] } } })).toBe(false);
});

test("a string's language is read from its key, then from its first characters", () => {
  expect(languageOf("html", "<p>")).toBe("html");
  expect(languageOf("body", "<!DOCTYPE html><html>")).toBe("html");
  expect(languageOf("style", "p { }")).toBe("css");
  expect(languageOf("script", "alert(1)")).toBe(""); // code, of a language it doesn't say
  expect(languageOf("source_ts", "let a")).toBe("typescript");
  expect(languageOf("code", "def main():")).toBe("python");
  expect(languageOf("query_sql", "select 1")).toBe("sql");
  expect(languageOf("markdown", "# Title")).toBe("markdown");
  expect(languageOf("source", "whatever")).toBe("");
  expect(languageOf("text", "Dear Alex,\nThanks.")).toBeNull();
  // A key is matched by its words, never by a part of one: prose stays prose.
  expect(languageOf("description", "A page that says hello.")).toBeNull();
  expect(languageOf("transcript", "Alice: hi\nBob: hello")).toBeNull();
  expect(languageOf("subscription", "monthly")).toBeNull();
  expect(languageOf("lifestyle", "quiet")).toBeNull();
  // A key named as an object's own members is a word like any other.
  expect(languageOf("constructor", "Dear Alex,\nThanks.")).toBeNull();
  expect(languageOf("to_string", "Dear Alex,\nThanks.")).toBeNull();
  expect(languageOf("body", "import { a } from './b';\nconst c = a;")).toBe("javascript");
  expect(languageOf("body", "import os\nprint(os.name)")).toBe("python");
});
