import { expect, test, vi } from "vitest";
import {
  failureLine,
  failureLogged,
  failureSaid,
  GENERIC,
  LONGEST,
  signInRefused,
} from "./failure";

/** A refused read as the client's `Refused` is: a status, the body in `detail`, and `said`. */
const refused = (status: number, detail: unknown, said: string) =>
  Object.assign(new Error(`the server refused the read (${status})`), { status, detail, said });

test("a refused read says the sentence the client chose for it", () => {
  expect(
    failureSaid(refused(403, { detail: { type: "forbidden" } }, "You may not see this.")),
  ).toBe("You may not see this.");
});

test("anything else says the generic sentence, whatever it holds", () => {
  const hostile = `${String.fromCodePoint(0x202e)}txt.exe <img src=x onerror=alert(1)> password=hunter2`;
  for (const error of [
    Object.assign(new Error(hostile), { status: 400, detail: hostile }),
    { status: 422, detail: { type: "validation_failed", message: hostile } },
    { said: 7 },
    new Error(hostile),
    hostile,
    null,
  ]) {
    expect(failureSaid(error)).toBe(GENERIC);
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
  expect(
    failureLine(
      `${"x".repeat(80)}_password=p1 CLIENTSECRET=c1 ${["sk", "abcdefgh12"].join("-")} ghp_${"a".repeat(24)} ${["eyJa", "eyJb", "c"].join(".")}`,
    ),
  ).toBe(
    `${"x".repeat(80)}_password=[redacted] CLIENTSECRET=[redacted] [redacted] [redacted] [redacted]`,
  );
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

test("the console line holds the server's words, scrubbed, and a thrown refusal's whole", () => {
  const detail = { type: "invalid", message: "grantr is down\nat db-1", password: "hunter2" };
  const read = Object.assign(new Error("the server refused the read (503)"), {
    status: 503,
    detail,
    said: "The server had a problem. Try again in a moment.",
  });
  const line = failureLine(read);
  expect(line).toContain("grantr is down");
  expect(line).toContain("status=503");
  expect(line).not.toContain("hunter2");
  expect(line).not.toContain("\n");
  const thrown = failureLine({ status: 422, detail: "token=abc123 x" });
  expect(thrown).toContain("status=422");
  expect(thrown).not.toContain("[object Object]");
  expect(thrown).not.toContain("abc123");
});

test("signing in refused says the kit's words, never Supabase's, and logs the whole", () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  try {
    const wrong = { name: "AuthApiError", status: 400, code: "invalid_credentials", message: "x" };
    expect(signInRefused(wrong)).toBe("That email and password don't match an account.");
    expect(signInRefused({ status: 429, message: "<b>slow</b>" })).toBe(
      "Too many tries. Wait a moment, then try again.",
    );
    expect(signInRefused(new Error("password=hunter2 upstream"))).toBe(GENERIC);
    expect(warned).toHaveBeenCalledTimes(3);
    expect(String(warned.mock.calls.at(-1)?.[1])).not.toContain("hunter2");
  } finally {
    warned.mockRestore();
  }
});
