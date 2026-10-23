import { expect, test } from "vitest";
import { pathsOf, reasons, refusalSaid } from "./reasons";

const HIDDEN = String.fromCodePoint(0x202e);
/** A detail as a hostile or careless server might send it: long, on lines, with markup, a
 * direction override and a secret. */
const HOSTILE = `${HIDDEN}txt.exe\n<img src=x onerror=alert(1)>\npassword=hunter2 ${"x".repeat(5000)}`;

test("no words of a server's reach the reader, however the refusal carries them", () => {
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
      const said = [refusalSaid(status, body), ...reasons(status, body)].join(" ");
      for (const part of ["hunter2", "img", "onerror", "txt.exe", HIDDEN, "\n", "xxxx"]) {
        expect(said).not.toContain(part);
      }
      expect(said.length).toBeLessThan(200);
    }
  }
});

test("values that aren't valid are said with where they are, the fields' paths alone", () => {
  expect(
    refusalSaid(422, {
      detail: [
        { loc: ["body", "command", "install_rule", "rule", "when"], msg: "Field required" },
        { loc: ["query", "start"], msg: "Input should be a valid datetime" },
        { loc: ["body", "items", 2, "name"], msg: "too long" },
      ],
    }),
  ).toBe("What was asked for isn't valid: rule.when, start, items.2.name.");
  expect(
    refusalSaid(422, {
      rejection: { type: "validation_failed", errors: [{ loc: ["answer", "email"], msg: "no" }] },
    }),
  ).toBe("What was asked for isn't valid: answer.email.");
  expect(pathsOf([{ loc: ["body", "a b"] }, { loc: ["body", "x".repeat(65)] }, "loc"])).toEqual([]);
});

test("a known code, then the status, says the sentence; a command's forbidden is an action's", () => {
  expect(refusalSaid(403, { detail: { type: "forbidden" } })).toBe("You may not see this.");
  expect(reasons(403, { detail: { type: "forbidden" } })).toEqual(["You may not do this here."]);
  expect(refusalSaid(409, { detail: { type: "artifact_busy" } })).toBe(
    "Someone else has it now. Try again once they're done.",
  );
  expect(refusalSaid(413, null)).toBe("That's too large.");
  expect(refusalSaid(418, null)).toBe("Something went wrong. Try again in a moment.");
});
