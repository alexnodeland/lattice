import type { Server } from "bun";
import { afterAll, beforeAll, beforeEach, expect, test } from "vitest";
import { answerConsent, readConsent } from "./consent";
import { createApi } from "./rest";

interface Asked {
  readonly method: string;
  readonly path: string;
  readonly tenant: string | null;
  readonly body: unknown;
}

const asked: Asked[] = [];
let given = false;
let sessions = 0;
let down = false;
let server: Server<unknown>;
let api: ReturnType<typeof createApi>;

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    async fetch(request) {
      const url = new URL(request.url);
      const text = await request.text();
      asked.push({
        method: request.method,
        path: url.pathname,
        tenant: request.headers.get("x-tenant"),
        body: text ? JSON.parse(text) : null,
      });
      if (down) {
        return new Response("down", { status: 503 });
      }
      if (url.pathname === "/portalr/v1/analytics/consent") {
        if (request.method === "PUT") {
          given = (JSON.parse(text) as { given: boolean }).given;
          return Response.json({ given, deleted: given ? null : true });
        }
        return Response.json({ given, deleting: false });
      }
      if (url.pathname === "/portalr/v1/analytics/session") {
        sessions += 1;
        return Response.json({ session: `s${sessions}` });
      }
      return Response.json({ recorded: 1, dropped: 0 }, { status: 202 });
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  api = createApi(
    { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
    () => ({ token: "t0k3n" }),
  );
});

afterAll(() => server.stop(true));

beforeEach(() => {
  asked.length = 0;
  given = false;
  sessions = 0;
  down = false;
});

test("the answer is no until the person says yes, and no where the relay can't be read", async () => {
  expect(await readConsent(api)).toEqual({ given: false, deleting: false });
  expect(await answerConsent(api, true)).toEqual({ given: true, deleted: null });
  expect(await readConsent(api)).toEqual({ given: true, deleting: false });
  down = true;
  expect(await readConsent(api)).toEqual({ given: false, deleting: false });
  await expect(answerConsent(api, false)).rejects.toThrow("the answer wasn't recorded (503)");
});
