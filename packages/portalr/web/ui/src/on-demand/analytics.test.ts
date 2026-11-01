import type { Api } from "@portalr/client";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { BATCH, Capture, WAIT } from "./analytics";

interface Sent {
  readonly path: string;
  readonly tenant: string | undefined;
  readonly body: unknown;
}

const sent: Sent[] = [];
let down = false;
let sessions = 0;
/** The sessions the relay no longer takes, as one past its hours. */
const stale = new Set<string>();

/** The relay, as the portal's client reaches it: a session, and batches of events. */
const api = {
  portalr: {
    POST: async (
      _command: null,
      path: string,
      init?: { headers?: Record<string, string>; body?: unknown },
    ) => {
      sent.push({ path, tenant: init?.headers?.["X-Tenant"], body: init?.body ?? null });
      if (down) {
        return { data: undefined, response: new Response(null, { status: 503 }) };
      }
      if (path === "/portalr/v1/analytics/session") {
        sessions += 1;
        return { data: { session: `s${sessions}` }, response: new Response(null) };
      }
      const { session } = (init?.body ?? { session: "" }) as { session: string };
      return stale.has(session)
        ? { data: undefined, response: new Response(null, { status: 403 }) }
        : { data: { recorded: 1, dropped: 0 }, response: new Response(null, { status: 202 }) };
    },
  },
} as unknown as Api;

const batches = () => sent.filter((s) => s.path === "/portalr/v1/events");
const signings = () => sent.filter((s) => s.path === "/portalr/v1/analytics/session");

beforeEach(() => {
  sent.length = 0;
  down = false;
  sessions = 0;
  stale.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

test("events gather and go in one batch, under one signed session, in the tenant", async () => {
  const capture = new Capture(api, "acme");
  capture.record({ event: "app.page.viewed.v1", route: "/t/$tenant" });
  capture.record({ event: "app.thread.opened.v1" });
  await capture.flush();
  capture.record({ event: "app.message.sent.v1" });
  await capture.flush();
  expect(batches().map((b) => b.tenant)).toEqual(["acme", "acme"]);
  expect(batches()[0]?.body).toEqual({
    session: "s1",
    events: [
      { event: "app.page.viewed.v1", route: "/t/$tenant" },
      { event: "app.thread.opened.v1" },
    ],
  });
  expect(signings()).toHaveLength(1);
});

test("a few events go after a while, and a full batch at once", async () => {
  const capture = new Capture(api, "acme");
  capture.record({ event: "app.page.viewed.v1" });
  await vi.advanceTimersByTimeAsync(WAIT - 1);
  expect(batches()).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(1);
  expect(batches()).toHaveLength(1);
  for (let n = 0; n < BATCH; n += 1) {
    capture.record({ event: "app.page.viewed.v1" });
  }
  await vi.advanceTimersByTimeAsync(0);
  expect(batches()).toHaveLength(2);
});

test("a session the relay no longer takes is signed afresh, and the batch sent again, once", async () => {
  const capture = new Capture(api, "acme");
  capture.record({ event: "app.page.viewed.v1" });
  await capture.flush();
  stale.add("s1");
  capture.record({ event: "app.thread.opened.v1" });
  await capture.flush();
  expect(signings()).toHaveLength(2);
  expect(batches().map((b) => (b.body as { session: string }).session)).toEqual(["s1", "s1", "s2"]);
  stale.add("s2");
  stale.add("s3");
  capture.record({ event: "app.thread.opened.v1" });
  await capture.flush();
  expect(signings()).toHaveLength(3);
  expect(batches()).toHaveLength(5);
});

test("a batch with no session is dropped, and a session is asked for again", async () => {
  const capture = new Capture(api, "acme");
  down = true;
  capture.record({ event: "app.page.viewed.v1" });
  await capture.flush();
  expect(sent.map((s) => s.path)).toEqual(["/portalr/v1/analytics/session"]);
  down = false;
  capture.record({ event: "app.page.viewed.v1" });
  await capture.flush();
  expect(batches()).toHaveLength(1);
  await capture.flush();
  expect(batches()).toHaveLength(1);
});

test("closed, as the person says no, what waits is dropped and nothing is sent after", async () => {
  const capture = new Capture(api, "acme");
  capture.record({ event: "app.page.viewed.v1" });
  capture.close();
  await vi.advanceTimersByTimeAsync(WAIT * 2);
  capture.record({ event: "app.page.viewed.v1" });
  await capture.flush();
  for (let n = 0; n < BATCH; n += 1) {
    capture.record({ event: "app.page.viewed.v1" });
  }
  await vi.advanceTimersByTimeAsync(WAIT * 2);
  expect(sent).toEqual([]);
});

test("a batch the relay refuses outright is dropped, and never fails the page", async () => {
  const refusing = {
    portalr: {
      POST: async (_command: null, path: string) => {
        if (path === "/portalr/v1/events") {
          throw new Error("the relay is down");
        }
        return { data: { session: "s" }, response: new Response(null) };
      },
    },
  } as unknown as Api;
  const capture = new Capture(refusing, "acme");
  capture.record({ event: "app.page.viewed.v1" });
  await expect(capture.flush()).resolves.toBeUndefined();
});

test("the signed session is handed on while it is held, and null once the person stops", async () => {
  const carried: (string | null)[] = [];
  const capture = new Capture(api, "acme", (session) => carried.push(session));
  capture.record({ event: "app.page.viewed.v1" });
  await capture.flush();
  expect(carried).toEqual(["s1"]);
  capture.close();
  expect(carried).toEqual(["s1", null]);
});

test("a session that couldn't be signed is handed on as none", async () => {
  down = true;
  const carried: (string | null)[] = [];
  const capture = new Capture(api, "acme", (session) => carried.push(session));
  capture.record({ event: "app.page.viewed.v1" });
  await capture.flush();
  expect(carried).toEqual([null]);
});
