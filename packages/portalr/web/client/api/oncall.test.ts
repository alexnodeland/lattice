import { afterEach, expect, test } from "vitest";
import { reflexr } from "../src/reflexr";
import { createApi } from "../src/rest";
import { streamUrl } from "../src/session";
import { Stream } from "../src/stream";
import { until } from "../src/test/until";
import { applied, every, session, surface, workspace } from "./resume";

const base = surface("REFLEXR_URL");
const api = createApi({ artifactr: base, reflexr: base, grantr: base }, () => session);
let close = () => {};

afterEach(() => close());

async function publish(ws: string, n: number): Promise<void> {
  const { data } = await api.reflexr.POST("/workspaces/{workspace_id}/events", {
    params: { path: { workspace_id: ws } },
    body: {
      id: `evt_portalr_${n}`,
      event: {
        type: "oncall:alert.fired",
        service: "checkout",
        severity: 3,
        message: `alert ${n}`,
      },
    },
  });
  expect(data?.[0]?.duplicate).toBe(false);
}

test("a client resumes oncall's stream across a dropped connection, losing and repeating nothing", async () => {
  const ws = workspace();
  const store = new Stream(reflexr, { url: streamUrl(base, ws, session) });
  close = () => store.close();
  const seqs = applied(store);
  store.open();
  await until(store, (s) => s.status === "live");
  await publish(ws, 1);
  await until(store, (s) => s.seq >= 1);

  // The connection drops, and alerts are published while the client is away.
  store.reconnect();
  await publish(ws, 2);
  await publish(ws, 3);

  const { data: log } = await api.reflexr.GET("/workspaces/{workspace_id}/events", {
    params: { path: { workspace_id: ws } },
  });
  const head = Math.max(...(log ?? []).map((envelope) => envelope.seq));
  await until(store, (s) => s.status === "live" && s.seq >= head);
  expect(seqs.slice(0, head)).toEqual(every(head));
});
