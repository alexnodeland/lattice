import type { Api } from "@portalr/client";
import { beforeEach, expect, test } from "vitest";
import { BATCH, Capture, WAIT } from "./analytics";

interface Sent {
  readonly path: string;
  readonly tenant: string | undefined;
  readonly body: unknown;
}

const sent: Sent[] = [];
let down = false;
let sessions = 0;

/** The relay, as the portal's client reaches it: a session, and batches of events. */
const api = {
  portalr: {
    POST: async (path: string, init?: { headers?: Record<string, string>; body?: unknown }) => {
      sent.push({ path, tenant: init?.headers?.["X-Tenant"], body: init?.body ?? null });
      if (down) {
        return { data: undefined };
      }
      if (path === "/portalr/v1/analytics/session") {
        sessions += 1;
        return { data: { session: `s${sessions}` } };
      }
      return { data: { recorded: 1, dropped: 0 } };
    },
  },
} as unknown as Api;

const batches = () => sent.filter((s) => s.path === "/portalr/v1/events");

async function until(check: () => boolean): Promise<void> {
  for (let n = 0; n < 200 && !check(); n += 1) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

beforeEach(() => {
  sent.length = 0;
  down = false;
  sessions = 0;
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
      { event: "app.page.viewed.v1", route: "/t/$tenant", props: {} },
      { event: "app.thread.opened.v1", props: {} },
    ],
  });
  expect(sessions).toBe(1);
});

test("a full batch goes at once, and a few go after a while", async () => {
  const capture = new Capture(api, "acme", 20);
  capture.record({ event: "app.page.viewed.v1" });
  expect(batches()).toHaveLength(0);
  await until(() => batches().length === 1);
  expect(batches()).toHaveLength(1);
  for (let n = 0; n < BATCH; n += 1) {
    capture.record({ event: "app.page.viewed.v1" });
  }
  await until(() => batches().length === 2);
  expect(batches()).toHaveLength(2);
  expect(WAIT).toBeGreaterThan(20);
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

test("a batch the relay refuses outright is dropped, and never fails the page", async () => {
  const refusing = {
    portalr: {
      POST: async (path: string) => {
        if (path === "/portalr/v1/events") {
          throw new Error("the relay is down");
        }
        return { data: { session: "s" } };
      },
    },
  } as unknown as Api;
  const capture = new Capture(refusing, "acme");
  capture.record({ event: "app.page.viewed.v1" });
  await expect(capture.flush()).resolves.toBeUndefined();
});
