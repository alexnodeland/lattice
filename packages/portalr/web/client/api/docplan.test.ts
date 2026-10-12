import { afterEach, expect, test } from "vitest";
import { artifactr } from "../src/artifactr";
import { createApi } from "../src/rest";
import { streamUrl } from "../src/session";
import { Stream } from "../src/stream";
import { until } from "../src/test/until";
import { applied, every, session, surface, workspace } from "./resume";

const base = surface("ARTIFACTR_URL");
const api = createApi({ artifactr: base, reflexr: base, grantr: base }, () => session);
let close = () => {};

afterEach(() => close());

test("a client resumes docplan's stream across a dropped connection, losing and repeating nothing", async () => {
  const ws = workspace();
  const store = new Stream(artifactr, { url: streamUrl(base, ws, session) });
  close = () => store.close();
  const seqs = applied(store);
  store.open();
  await until(store, (s) => s.status === "live");

  const created = await store.send({ type: "create_thread", thread_id: "thr_1", title: "Launch" });
  expect(created.done).toBe(true);
  await store.send({ type: "post_message", thread_id: "thr_1", content: "Draft the plan" });
  // The agent's turn, on pydantic-ai's test model, ends.
  await until(store, (s) => Object.values(s.state.runs).some((run) => run.status !== "running"));

  // The connection drops, and two notices are posted over REST while the client is away.
  store.reconnect();
  for (const n of [1, 2]) {
    const { data } = await api.artifactr.POST("/workspaces/{workspace_id}/commands", {
      params: { path: { workspace_id: ws } },
      body: {
        type: "command",
        command_id: `notice-${n}`,
        command: {
          type: "post_message",
          thread_id: "thr_1",
          content: `notice ${n}`,
          kind: "notice",
        },
      },
    });
    expect(data?.ok).toBe(true);
  }

  const { data: tail } = await api.artifactr.GET("/workspaces/{workspace_id}/events", {
    params: { path: { workspace_id: ws }, query: { last: 1 } },
  });
  const head = tail?.at(-1)?.seq ?? 0;
  const { state } = await until(store, (s) => s.status === "live" && s.seq === head);
  expect(seqs).toEqual(every(head));
  const notices = state.threads.thr_1?.messages.filter((m) => m.kind === "notice") ?? [];
  expect(notices.map((m) => m.content)).toEqual(["notice 1", "notice 2"]);
});
