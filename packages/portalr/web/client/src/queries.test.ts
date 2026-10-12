import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import type * as v1 from "./generated/artifactr.v1";
import type * as reflexrV1 from "./generated/reflexr.v1";
import { createQueries, keys, stale } from "./queries";
import { createApi } from "./rest";

interface Seen {
  readonly method: string;
  readonly url: URL;
  readonly headers: Headers;
  readonly body: unknown;
}

const seen: Seen[] = [];
const ME = { tenant: "acme", roles: ["owner"], workspaces: ["ws_1"] };
const MEMBERSHIPS = [{ tenant: "acme", user: "alice", roles: ["owner"] }];
let origin: string;
let server: Server<unknown>;
let queries: ReturnType<typeof createQueries>;

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    async fetch(request) {
      const url = new URL(request.url);
      const body = request.method === "POST" ? await request.json() : null;
      seen.push({ method: request.method, url, headers: request.headers, body });
      if (url.pathname.endsWith("/missing")) {
        return Response.json({ detail: "not found" }, { status: 404 });
      }
      if (url.pathname === "/grantr/v1/me") {
        return Response.json(request.headers.has("x-tenant") ? ME : { memberships: MEMBERSHIPS });
      }
      return Response.json(url.pathname.endsWith("/checks") ? [true, false] : []);
    },
  });
  origin = `http://127.0.0.1:${server.port}`;
  const api = createApi(
    { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
    () => ({ token: "t0k3n", tenant: "acme" }),
  );
  queries = createQueries(api);
});

afterAll(() => {
  server.stop(true);
});

test("a read goes to its surface, with the session", async () => {
  await new QueryClient().fetchQuery(queries.artifactr.tail("ws_1", "thr_1", 50));
  const request = seen.at(-1);
  expect(request?.url.pathname).toBe("/artifactr/v1/workspaces/ws_1/events");
  expect(request?.url.searchParams.getAll("thread_id")).toEqual(["thr_1"]);
  expect(request?.url.searchParams.get("last")).toBe("50");
  expect(request?.headers.get("authorization")).toBe("Bearer t0k3n");
  expect(request?.headers.get("x-tenant")).toBe("acme");
});

test("every read has its own path", async () => {
  const client = new QueryClient();
  const reads = [
    [queries.artifactr.workspaces(), "/artifactr/v1/workspaces"],
    [queries.artifactr.threads("ws_1"), "/artifactr/v1/workspaces/ws_1/threads"],
    [queries.artifactr.thread("ws_1", "thr_1"), "/artifactr/v1/workspaces/ws_1/threads/thr_1"],
    [queries.artifactr.artifacts("ws_1"), "/artifactr/v1/workspaces/ws_1/artifacts"],
    [
      queries.artifactr.artifact("ws_1", "plan_1"),
      "/artifactr/v1/workspaces/ws_1/artifacts/plan_1",
    ],
    [queries.artifactr.proposals("ws_1"), "/artifactr/v1/workspaces/ws_1/proposals"],
    [queries.reflexr.rules("ws_1"), "/reflexr/v1/workspaces/ws_1/rules"],
    [queries.reflexr.runs("ws_1"), "/reflexr/v1/workspaces/ws_1/runs"],
  ] as const;
  for (const [options, path] of reads) {
    await client.fetchQuery(options as unknown as Parameters<QueryClient["fetchQuery"]>[0]);
    expect(seen.at(-1)?.url.pathname).toBe(path);
  }
});

test("grantr says who the caller is in the session's tenant, or lists every one without it", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const signedIn = createQueries(
    createApi({ artifactr: "", reflexr: "", grantr: origin }, () => ({ token: "t", tenant: null })),
  );
  expect(await client.fetchQuery(queries.grantr.me("acme"))).toEqual(ME);
  expect(seen.at(-1)?.headers.get("x-tenant")).toBe("acme");
  expect(await client.fetchQuery(signedIn.grantr.memberships())).toEqual(MEMBERSHIPS);
  expect(seen.at(-1)?.headers.get("x-tenant")).toBeNull();
  // Each is the wrong question for the other session.
  await expect(client.fetchQuery(signedIn.grantr.me("acme"))).rejects.toThrow(/every tenant/);
  client.clear();
  await expect(client.fetchQuery(queries.grantr.memberships())).rejects.toThrow(/one tenant/);
});

test("checks are asked in one call, and answered in order", async () => {
  const checks = [
    { action: "artifactr:edit_artifact", resource: { kind: "workspace", workspace: "ws_1" } },
    { action: "artifactr:respond_to_proposal", resource: { kind: "workspace", workspace: "ws_1" } },
  ] as Parameters<typeof queries.grantr.checks>[1];
  const answers = await new QueryClient().fetchQuery(queries.grantr.checks("acme", checks));
  expect(answers).toEqual([true, false]);
  expect(seen.at(-1)).toMatchObject({ method: "POST", body: checks });
});

test("a refused read throws", async () => {
  await expect(
    new QueryClient({ defaultOptions: { queries: { retry: false } } }).fetchQuery(
      queries.artifactr.thread("ws_1", "missing"),
    ),
  ).rejects.toThrow(/refused/);
});

test("keys nest under their workspace, so invalidating it refetches its reads", () => {
  const workspace = keys.artifactr.workspace("ws_1");
  for (const key of [
    keys.artifactr.threads("ws_1"),
    keys.artifactr.artifact("ws_1", "plan_1"),
    keys.artifactr.tail("ws_1", "thr_1", 50),
  ]) {
    expect(key.slice(0, workspace.length)).toEqual(workspace);
  }
  expect(keys.reflexr.runs("ws_1").slice(0, 3)).toEqual(keys.reflexr.workspace("ws_1"));
});

test("a list's key doesn't prefix its details' or the tail's, so a list refetches alone", () => {
  const list = keys.artifactr.threads("ws_1");
  for (const key of [
    keys.artifactr.thread("ws_1", "thr_1"),
    keys.artifactr.tail("ws_1", "thr_1", 50),
  ]) {
    expect(key.slice(0, list.length)).not.toEqual(list);
  }
});

const artifactrFrame = (event: Record<string, unknown>) =>
  ({ type: "event", seq: 1, event }) as unknown as v1.EventFrame;
const reflexrFrame = (type: string) =>
  ({ type: "event", seq: 1, event: { type } }) as reflexrV1.EventFrame;

test("an artifactr event makes stale the reads it changes", () => {
  expect(
    stale.artifactr("ws_1", artifactrFrame({ type: "artifact_changed", artifact_id: "plan_1" })),
  ).toEqual([keys.artifactr.artifacts("ws_1"), keys.artifactr.artifact("ws_1", "plan_1")]);
  expect(
    stale.artifactr("ws_1", artifactrFrame({ type: "thread_created", thread_id: "t" })),
  ).toEqual([keys.artifactr.threads("ws_1")]);
  expect(
    stale.artifactr("ws_1", artifactrFrame({ type: "focus_changed", thread_id: "t" })),
  ).toEqual([keys.artifactr.threads("ws_1"), keys.artifactr.thread("ws_1", "t")]);
  expect(stale.artifactr("ws_1", artifactrFrame({ type: "proposal_created" }))).toEqual([
    keys.artifactr.proposals("ws_1"),
  ]);
  expect(
    stale.artifactr("ws_1", artifactrFrame({ type: "proposal_resolved", artifact_id: "plan_1" })),
  ).toEqual([
    keys.artifactr.proposals("ws_1"),
    keys.artifactr.artifacts("ws_1"),
    keys.artifactr.artifact("ws_1", "plan_1"),
  ]);
  expect(stale.artifactr("ws_1", artifactrFrame({ type: "message_posted" }))).toEqual([]);
  expect(stale.artifactr("ws_1", artifactrFrame({ type: "something_new" }))).toEqual([]);
});

test("reflexr's rule events make its rules stale, and its run events its runs", () => {
  expect(stale.reflexr("ws_1", reflexrFrame("reflexr:rule_installed"))).toEqual([
    keys.reflexr.rules("ws_1"),
  ]);
  expect(stale.reflexr("ws_1", reflexrFrame("reflexr:run_succeeded"))).toEqual([
    keys.reflexr.runs("ws_1"),
  ]);
  expect(stale.reflexr("ws_1", reflexrFrame("ops:alert.fired"))).toEqual([]);
});
