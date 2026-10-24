import { expect, test } from "vitest";
import { pathsOf } from "./paths";
import { invalidSaid, refusalSaid, runOn } from "./reasons";

const HIDDEN = String.fromCodePoint(0x202e);
/** A detail as a hostile or careless server might send it: long, on lines, with markup, a
 * direction override and a secret. */
const HOSTILE = `${HIDDEN}txt.exe\n<img src=x onerror=alert(1)>\npassword=hunter2 ${"x".repeat(5000)}`;

test("no words of a server's reach the reader, however the refusal carries them", async () => {
  const bodies = [
    HOSTILE,
    { detail: HOSTILE },
    { detail: { type: "forbidden", message: HOSTILE } },
    { detail: { type: HOSTILE, message: HOSTILE } },
    { detail: { message: HOSTILE } },
    { rejection: { type: "validation_failed", message: HOSTILE, errors: [HOSTILE] } },
    { rejection: { type: "invalid_state", message: HOSTILE } },
    { detail: [{ loc: ["body", HOSTILE], msg: HOSTILE }] },
    { detail: [{ loc: [HOSTILE], msg: HOSTILE }] },
  ];
  for (const status of [400, 403, 404, 409, 422, 500, 503]) {
    for (const body of bodies) {
      const said = [await refusalSaid(status, body), await refusalSaid(status, body, true)].join(
        " ",
      );
      for (const part of ["hunter2", "img", "onerror", "txt.exe", HIDDEN, "\n", "xxxx"]) {
        expect(said).not.toContain(part);
      }
      expect(said.length).toBeLessThan(200);
    }
  }
});

test("values that aren't valid are said with where they are, the fields' paths alone", async () => {
  expect(
    await refusalSaid(422, {
      detail: [
        { loc: ["body", "command", "install_rule", "rule", "when"], msg: "Field required" },
        { loc: ["query", "start"], msg: "Input should be a valid datetime" },
        { loc: ["body", "items", 2, "name"], msg: "too long" },
      ],
    }),
  ).toBe("What was asked for isn't valid: rule.when, start, items.2.name.");
  expect(
    await refusalSaid(422, {
      rejection: { type: "validation_failed", errors: [{ loc: ["answer", "email"], msg: "no" }] },
    }),
  ).toBe("What was asked for isn't valid: answer.email.");
  expect(pathsOf([{ loc: ["body", "a b"] }, { loc: ["body", "x".repeat(65)] }, "loc"])).toEqual([]);
});

test("a known code, then the status, says the sentence; a command's forbidden is an action's", async () => {
  expect(await refusalSaid(403, { detail: { type: "forbidden" } })).toBe("You may not see this.");
  expect(await refusalSaid(403, { detail: { type: "forbidden" } }, true)).toBe(
    "You may not do this here.",
  );
  expect(await refusalSaid(409, { detail: { type: "artifact_busy" } })).toBe(
    "Someone else has it now.",
  );
  expect(await refusalSaid(413, null)).toBe("That's too large.");
  expect(await refusalSaid(418, null)).toBe("Something went wrong. Try again in a moment.");
});

test("paths are capped, and none names a secret-shaped key", () => {
  const many = Array.from({ length: 100 }, (_, at) => ({ loc: ["body", `field${at}`] }));
  expect(pathsOf(many)).toEqual(["field0", "field1", "field2", "field3", "field4"]);
  expect(
    pathsOf([
      { loc: ["body", "api_key"] },
      { loc: ["body", "access_token"] },
      { loc: ["body", "Password"] },
      { loc: ["body", "sk-abcdef123"] },
      { loc: ["body", "a", "b", "c", "d", "e", "f", "g"] },
      { loc: ["body", "ok"] },
    ]),
  ).toEqual(["ok"]);
  const long = Array.from({ length: 10 }, (_, at) => ({ loc: ["body", `${"p".repeat(30)}${at}`] }));
  expect(pathsOf(long).join(", ").length).toBeLessThanOrEqual(170);
  expect(invalidSaid([])).toBe("What was asked for isn't valid.");
  expect(invalidSaid(["a", "b"])).toBe("What was asked for isn't valid: a, b.");
});

test("a reason runs on after a colon in lower case, but a name keeps its capitals", () => {
  expect(runOn("You may not do this here.")).toBe("you may not do this here.");
  expect(runOn("Someone else has it now.")).toBe("someone else has it now.");
  expect(runOn("WordCraft couldn't read it.")).toBe("WordCraft couldn't read it.");
  expect(runOn("OK, done.")).toBe("OK, done.");
  expect(runOn("already lower")).toBe("already lower");
});
