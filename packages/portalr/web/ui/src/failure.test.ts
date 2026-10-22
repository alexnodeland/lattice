import { expect, test, vi } from "vitest";
import { failureSaid, LONGEST } from "./failure";

test("a failure's message starts its own sentence with a capital", () => {
  expect(failureSaid(new Error("the server refused the read (422): no"))).toBe(
    "The server refused the read (422): no",
  );
  expect(failureSaid("down")).toBe("Down");
  expect(failureSaid(new Error(""))).toBe("");
});

test("a server's words are shown as one plain line, controls and direction marks out, cut short", () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(failureSaid(new Error("the server refused the read (503):\ngrantr\tis down"))).toBe(
    "The server refused the read (503): grantr is down",
  );
  // A right-to-left override would turn what follows around; a zero-width space hides in it.
  expect(failureSaid(new Error("refused: ‮txt.exe‬ ​ok"))).toBe("Refused: txt.exe ok");
  // Markup is text: React writes it as written.
  expect(failureSaid(new Error("refused: <img src=x onerror=alert(1)>"))).toBe(
    "Refused: <img src=x onerror=alert(1)>",
  );
  const long = failureSaid(new Error(`refused: ${"x".repeat(500)}`));
  expect([...long]).toHaveLength(LONGEST);
  expect(long.endsWith("…")).toBe(true);
  // What was changed is kept, whole, in the console; a message that needs nothing isn't logged.
  expect(warned).toHaveBeenCalledTimes(3);
  failureSaid(new Error("down"));
  expect(warned).toHaveBeenCalledTimes(3);
  warned.mockRestore();
});
