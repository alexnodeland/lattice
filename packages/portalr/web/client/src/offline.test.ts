import { expect, test, vi } from "vitest";
import { checkIn } from "./files";
import { refusal } from "./queries";
import { refusalSaid } from "./reasons";

// The chunk that reads where values aren't valid fails to load, as offline or after a deploy.
vi.mock("./paths", () => {
  throw new Error("the chunk didn't load");
});

const INVALID = "What was asked for isn't valid.";
const LOCATED = { detail: [{ loc: ["body", "name"], msg: "Field required" }] };

test("a refusal whose paths can't load is said without them", async () => {
  expect(await refusalSaid(422, LOCATED)).toBe(INVALID);
});

test("a read refused so still carries its status and its wait", async () => {
  const answered = new Response(null, { status: 422, headers: { "retry-after": "5" } });
  const refused = await refusal(answered, LOCATED);
  expect([refused.status, refused.retryAfter, refused.said]).toEqual([422, 5, INVALID]);
});

test("an upload refused so still settles", async () => {
  let xhr: { status: number; responseText: string; onload: (() => void) | null } | undefined;
  vi.stubGlobal(
    "XMLHttpRequest",
    class {
      status = 0;
      responseText = "";
      upload = { onprogress: null };
      onload: (() => void) | null = null;
      constructor() {
        xhr = this;
      }
      open() {}
      setRequestHeader() {}
      send() {}
      abort() {}
    },
  );
  try {
    const answer = checkIn({
      surface: "/artifactr/v1",
      session: { token: "t" },
      tenant: "acme",
      workspace: "ws_1",
      checkout: "co_1",
      file: new Blob(["x"]),
    });
    if (xhr === undefined) {
      throw new Error("nothing was sent");
    }
    xhr.status = 422;
    xhr.responseText = JSON.stringify(LOCATED);
    xhr.onload?.();
    expect(await answer).toEqual({ outcome: "refused", status: 422, reasons: [INVALID] });
  } finally {
    vi.unstubAllGlobals();
  }
});
