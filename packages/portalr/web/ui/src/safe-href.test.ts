import { expect, test } from "vitest";
import { safeHref } from "./safe-href";

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
    "http:foo",
    "https:/foo",
    "HTTP:example.com",
    "/relative/path",
    "not a url",
    "",
    null,
    undefined,
  ]) {
    expect(safeHref(bad), String(bad)).toBeNull();
  }
});
