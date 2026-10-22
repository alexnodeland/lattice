import { expect, test, vi } from "vitest";
import { failureLine, failureLogged, failureSaid, GENERIC, LONGEST } from "./failure";

/** A refusal as the client's `Refused` is: a status, and the body in `detail`. */
const refused = (status: number, detail: unknown) =>
  Object.assign(new Error(`the server refused the read (${status})`), { status, detail });

test("a known reason code says its own sentence", () => {
  expect(failureSaid(refused(403, { detail: { type: "forbidden", message: "bob may not" } }))).toBe(
    "You may not see this.",
  );
  expect(failureSaid(refused(409, { rejection: { type: "not_enabled" } }))).toBe(
    "This is switched off for this workspace. Ask an admin to switch it on.",
  );
});

test("an unknown or missing reason code says what its status does, or the generic sentence", () => {
  expect(failureSaid(refused(404, { detail: { type: "made_up" } }))).toBe(
    "It isn't there: it may have been moved or archived.",
  );
  expect(failureSaid(refused(503, "grantr is down"))).toBe(
    "The server had a problem. Try again in a moment.",
  );
  expect(failureSaid(refused(418, {}))).toBe(GENERIC);
  expect(failureSaid(refused(400, { detail: { type: "toString" } }))).toBe(GENERIC);
  expect(failureSaid(new Error("fetch failed"))).toBe(GENERIC);
  expect(failureSaid("down")).toBe(GENERIC);
});

test("a server's words never reach the reader", () => {
  const hostile = `${String.fromCodePoint(0x202e)}txt.exe <img src=x onerror=alert(1)> password=hunter2`;
  for (const error of [
    refused(400, { detail: hostile }),
    refused(422, { detail: { type: hostile, message: hostile } }),
    new Error(hostile),
  ]) {
    const said = failureSaid(error);
    expect(said).not.toContain("hunter2");
    expect(said).not.toContain("img");
    expect(said).not.toContain(String.fromCodePoint(0x202e));
  }
});

test("the console line is one line, with nothing hidden in it and secrets out", () => {
  expect(failureLine(new Error("refused (503):\ngrantr\tis down"))).toBe(
    "refused (503): grantr is down",
  );
  // A right-to-left override, isolates, a zero-width space, tag characters and blank fillers go.
  const hidden = [0x202e, 0x2066, 0x2069, 0x200b, 0xe0041, 0xe007f, 0x3164, 0x2800];
  const mixed = hidden.map((point, at) => "abcdefgh"[at] + String.fromCodePoint(point)).join("");
  expect(failureLine(new Error(mixed))).toBe("abcdefgh");
  // A family emoji's joiners stay, so it stays one.
  const family = String.fromCodePoint(0x1f468, 0x200d, 0x1f469, 0x200d, 0x1f467);
  expect(failureLine(family)).toBe(family);
  expect(
    failureLine("GET https://u:p@x.example/a?token=t1 api_key=k1 Bearer abc client_secret: s2"),
  ).toBe("GET https://x.example/a api_key=[redacted] Bearer [redacted] client_secret: [redacted]");
});

test("a long console line is cut between graphemes", () => {
  const flag = "\u{1f1f3}\u{1f1f4}";
  const line = failureLine(`${"x".repeat(LONGEST - 2)}${flag.repeat(3)}`);
  const graphemes = Array.from(new Intl.Segmenter().segment(line), ({ segment }) => segment);
  expect(graphemes).toHaveLength(LONGEST);
  expect(graphemes.at(-2)).toBe(flag);
  expect(graphemes.at(-1)).toBe("…");
});

test("a failure is logged once", () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  const error = new Error("down");
  failureLogged(error);
  failureLogged(error);
  expect(warned).toHaveBeenCalledTimes(1);
  expect(warned).toHaveBeenCalledWith("A failure, for operators:", "down");
  warned.mockRestore();
});
