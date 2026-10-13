import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import type * as v1 from "./generated/artifactr.v1";
import type * as reflexrV1 from "./generated/reflexr.v1";
import { AUDIT_PAGE, createQueries, keys, stale } from "./queries";
import { createApi, readConfig } from "./rest";

interface Seen {
  readonly method: string;
  readonly url: URL;
  readonly headers: Headers;
  readonly body: unknown;
}

const seen: Seen[] = [];
const CONFIG = {
  supabase: { url: "/", key: "sb_publishable_x" },
  surfaces: {
    artifactr: "/artifactr/v1",
    reflexr: "/reflexr/v1",
    grantr: "",
    portalr: "/portalr/v1",
  },
  readers: { tempo: true },
};
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
      if (url.pathname.endsWith("/missing") || url.pathname.startsWith("/missing/")) {
        return Response.json({ detail: "not found" }, { status: 404 });
      }
      if (url.pathname === "/portalr/v1/deployment/tenants") {
        const operator = request.headers.get("authorization") === "Bearer t0k3n";
        return operator
          ? Response.json({ tenants: ["acme"], spend: { status: "unconfigured" } })
          : request.headers.get("authorization") === "Bearer wrong"
            ? Response.json(
                { detail: { type: "forbidden", message: "not an operator" } },
                { status: 403 },
              )
            : Response.json({ detail: "the proxy refused" }, { status: 403 });
      }
      if (url.pathname === "/portalr/config.json") {
        return Response.json(CONFIG);
      }
      if (url.pathname === "/grantr/v1/me") {
        const tenant = request.headers.get("x-tenant");
        const forOne = request.headers.get("authorization") === "Bearer wrong";
        return Response.json(
          (tenant !== null && tenant !== "confused") || forOne ? ME : { memberships: MEMBERSHIPS },
        );
      }
      if (url.pathname.endsWith("/audit")) {
        // Sixty entries, the last of them before before_seq: a full page, and then ten.
        const before = Number(url.searchParams.get("before_seq") ?? 61);
        const last = Number(url.searchParams.get("last"));
        const seqs = Array.from({ length: 60 }, (_, index) => index + 1).filter(
          (seq) => seq < before,
        );
        return Response.json(seqs.slice(Math.max(seqs.length - last, 0)).map((seq) => ({ seq })));
      }
      return Response.json(url.pathname.endsWith("/checks") ? [true, false] : []);
    },
  });
  origin = `http://127.0.0.1:${server.port}`;
  const api = createApi(
    { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
    () => ({ token: "t0k3n" }),
  );
  queries = createQueries(api);
});

afterAll(() => {
  server.stop(true);
});

test("a read goes to its surface, with the session", async () => {
  await new QueryClient().fetchQuery(queries.artifactr.tail("acme", "ws_1", "thr_1", 50));
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
    [queries.artifactr.workspaces("acme"), "/artifactr/v1/workspaces"],
    [queries.artifactr.threads("acme", "ws_1"), "/artifactr/v1/workspaces/ws_1/threads"],
    [
      queries.artifactr.thread("acme", "ws_1", "thr_1"),
      "/artifactr/v1/workspaces/ws_1/threads/thr_1",
    ],
    [queries.artifactr.artifacts("acme", "ws_1"), "/artifactr/v1/workspaces/ws_1/artifacts"],
    [
      queries.artifactr.artifact("acme", "ws_1", "plan_1"),
      "/artifactr/v1/workspaces/ws_1/artifacts/plan_1",
    ],
    [queries.artifactr.proposals("acme", "ws_1"), "/artifactr/v1/workspaces/ws_1/proposals"],
    [
      queries.artifactr.revisions("acme", "ws_1", "plan_1"),
      "/artifactr/v1/workspaces/ws_1/artifacts/plan_1/revisions",
    ],
    [queries.reflexr.rules("acme", "ws_1"), "/reflexr/v1/workspaces/ws_1/rules"],
    [queries.reflexr.runs("acme", "ws_1"), "/reflexr/v1/workspaces/ws_1/runs"],
    [
      queries.reflexr.rule("acme", "ws_1", "tickets:echo"),
      "/reflexr/v1/workspaces/ws_1/rules/tickets%3Aecho",
    ],
    [queries.reflexr.schedules("acme", "ws_1"), "/reflexr/v1/workspaces/ws_1/schedules"],
    [queries.grantr.members("acme"), "/grantr/v1/tenants/acme/members"],
    [queries.grantr.groups("acme"), "/grantr/v1/tenants/acme/groups"],
    [queries.grantr.grants("acme"), "/grantr/v1/tenants/acme/grants"],
    [queries.grantr.roles("acme"), "/grantr/v1/tenants/acme/roles"],
    [queries.grantr.catalog(), "/grantr/v1/catalog"],
    [queries.grantr.keyring("acme"), "/grantr/v1/tenants/acme/keys"],
    [queries.portalr.spend("acme"), "/portalr/v1/spend"],
    [
      queries.portalr.feedback("acme", {
        start: "2026-10-07T00:00:00Z",
        end: "2026-10-14T00:00:00Z",
      }),
      "/portalr/v1/feedback",
    ],
    [queries.portalr.links("ops", "t1"), "/portalr/v1/deployment/links"],
    [queries.grantr.grants("acme", "ws_1"), "/grantr/v1/tenants/acme/grants"],
    [queries.grantr.restrictions("acme", "ws_1"), "/grantr/v1/tenants/acme/restrictions"],
  ] as const;
  for (const [options, path] of reads) {
    await client.fetchQuery(options as unknown as Parameters<QueryClient["fetchQuery"]>[0]);
    expect(seen.at(-1)?.url.pathname).toBe(path);
  }
  const grantsRead = seen.find(
    (each) =>
      each.url.pathname === "/grantr/v1/tenants/acme/grants" &&
      each.url.searchParams.has("workspace"),
  );
  expect(grantsRead?.url.searchParams.get("workspace")).toBe("ws_1");
  expect(grantsRead?.headers.get("x-tenant")).toBe("acme");
  expect(seen.at(-1)?.url.searchParams.get("workspace")).toBe("ws_1");
  expect(seen.at(-1)?.headers.get("x-tenant")).toBe("acme");
});

test("grantr says who the caller is in the tenant a read names, or lists them all", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  expect(await client.fetchQuery(queries.grantr.me("acme"))).toEqual(ME);
  expect(seen.at(-1)?.headers.get("x-tenant")).toBe("acme");
  expect(await client.fetchQuery(queries.grantr.memberships("alice"))).toEqual(MEMBERSHIPS);
  expect(seen.at(-1)?.headers.get("x-tenant")).toBeNull();
});

test("an answer for the wrong question throws", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // The stand-in answers a tenant named `confused` for every tenant, and `wrong`'s token for one.
  await expect(client.fetchQuery(queries.grantr.me("confused"))).rejects.toThrow(/every tenant/);
  const wrong = createQueries(
    createApi({ artifactr: "", reflexr: "", grantr: origin }, () => ({ token: "wrong" })),
  );
  await expect(client.fetchQuery(wrong.grantr.memberships("alice"))).rejects.toThrow(/one tenant/);
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
      queries.artifactr.thread("acme", "ws_1", "missing"),
    ),
  ).rejects.toMatchObject({ status: 404, detail: { detail: "not found" } });
});

test("keys nest under their workspace, so invalidating it refetches its reads", () => {
  const workspace = keys.artifactr.workspace("acme", "ws_1");
  for (const key of [
    keys.artifactr.threads("acme", "ws_1"),
    keys.artifactr.artifact("acme", "ws_1", "plan_1"),
    keys.artifactr.tail("acme", "ws_1", "thr_1", 50),
  ]) {
    expect(key.slice(0, workspace.length)).toEqual(workspace);
  }
  // An artifact's revisions are under it, so its change refetches them too.
  const artifact = keys.artifactr.artifact("acme", "ws_1", "plan_1");
  expect(keys.artifactr.revisions("acme", "ws_1", "plan_1").slice(0, artifact.length)).toEqual(
    artifact,
  );
  expect(keys.reflexr.runs("acme", "ws_1").slice(0, 4)).toEqual(
    keys.reflexr.workspace("acme", "ws_1"),
  );
});

test("a list's key doesn't prefix its details' or the tail's, so a list refetches alone", () => {
  const list = keys.artifactr.threads("acme", "ws_1");
  for (const key of [
    keys.artifactr.thread("acme", "ws_1", "thr_1"),
    keys.artifactr.tail("acme", "ws_1", "thr_1", 50),
  ]) {
    expect(key.slice(0, list.length)).not.toEqual(list);
  }
});

const artifactrFrame = (event: Record<string, unknown>) =>
  ({ type: "event", seq: 1, event }) as unknown as v1.EventFrame;
const reflexrFrame = (type: string, fields: Record<string, unknown> = {}) =>
  ({ type: "event", seq: 1, event: { type, ...fields } }) as reflexrV1.EventFrame;

test("an artifactr event makes stale the reads it changes", () => {
  expect(
    stale.artifactr(
      "acme",
      "ws_1",
      artifactrFrame({ type: "artifact_changed", artifact_id: "plan_1" }),
    ),
  ).toEqual([
    keys.artifactr.artifacts("acme", "ws_1"),
    keys.artifactr.artifact("acme", "ws_1", "plan_1"),
  ]);
  expect(
    stale.artifactr("acme", "ws_1", artifactrFrame({ type: "thread_created", thread_id: "t" })),
  ).toEqual([keys.artifactr.threads("acme", "ws_1")]);
  expect(
    stale.artifactr("acme", "ws_1", artifactrFrame({ type: "focus_changed", thread_id: "t" })),
  ).toEqual([keys.artifactr.threads("acme", "ws_1"), keys.artifactr.thread("acme", "ws_1", "t")]);
  expect(stale.artifactr("acme", "ws_1", artifactrFrame({ type: "proposal_created" }))).toEqual([
    keys.artifactr.proposals("acme", "ws_1"),
  ]);
  expect(
    stale.artifactr(
      "acme",
      "ws_1",
      artifactrFrame({ type: "proposal_resolved", artifact_id: "plan_1" }),
    ),
  ).toEqual([
    keys.artifactr.proposals("acme", "ws_1"),
    keys.artifactr.artifacts("acme", "ws_1"),
    keys.artifactr.artifact("acme", "ws_1", "plan_1"),
  ]);
  expect(stale.artifactr("acme", "ws_1", artifactrFrame({ type: "message_posted" }))).toEqual([]);
  expect(stale.artifactr("acme", "ws_1", artifactrFrame({ type: "something_new" }))).toEqual([]);
});

test("reflexr's rule events make its rules stale, its run events its runs, and ticks its schedules", () => {
  expect(stale.reflexr("acme", "ws_1", reflexrFrame("reflexr:feedback_given"))).toEqual([]);
  expect(
    stale.reflexr("acme", "ws_1", reflexrFrame("reflexr:rule_archived", { rule: "tickets:echo" })),
  ).toEqual([
    keys.reflexr.rules("acme", "ws_1"),
    keys.reflexr.rule("acme", "ws_1", "tickets:echo"),
  ]);
  expect(stale.reflexr("acme", "ws_1", reflexrFrame("reflexr:tick"))).toEqual([
    keys.reflexr.schedules("acme", "ws_1"),
  ]);
  expect(stale.reflexr("acme", "ws_1", reflexrFrame("reflexr:run_succeeded"))).toEqual([
    keys.reflexr.runs("acme", "ws_1"),
  ]);
  expect(stale.reflexr("acme", "ws_1", reflexrFrame("ops:alert.fired"))).toEqual([]);
});

test("config.json is read from the deployment, or its failure said", async () => {
  expect(await readConfig(origin)).toEqual(CONFIG);
  await expect(readConfig(`${origin}/missing`)).rejects.toThrow(/config.json answered 404/);
});

const DAY = { start: "2026-10-11T00:00:00Z", end: "2026-10-12T00:00:00Z", step: 3600 };

test("portalr's reads name their tenant and window", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await client.fetchQuery(queries.portalr.metrics("acme", "failed_turns", DAY));
  const metrics = seen.at(-1);
  expect(metrics?.url.pathname).toBe("/portalr/v1/metrics");
  expect(Object.fromEntries(metrics?.url.searchParams ?? [])).toEqual({
    metric: "failed_turns",
    start: DAY.start,
    end: DAY.end,
    step: "3600",
    limit: "1000",
  });
  expect(metrics?.headers.get("x-tenant")).toBe("acme");
  await client.fetchQuery(queries.portalr.scores("acme", { start: DAY.start, end: DAY.end }));
  expect(seen.at(-1)?.url.pathname).toBe("/portalr/v1/scores");
  expect(seen.at(-1)?.url.searchParams.get("step")).toBeNull();
});

test("the deployment's tenants are an operator's, and null for anyone else", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  expect(await client.fetchQuery(queries.portalr.tenants("alice"))).toEqual({
    tenants: ["acme"],
    spend: { status: "unconfigured" },
  });
  const stranger = createQueries(
    createApi({ artifactr: "", reflexr: "", grantr: origin }, () => ({ token: "wrong" })),
  );
  expect(await new QueryClient().fetchQuery(stranger.portalr.tenants("bob"))).toBeNull();
  // A 403 that isn't grantr's or portalr's refusal, such as a proxy's, is no answer at all.
  const proxied = createQueries(
    createApi({ artifactr: "", reflexr: "", grantr: origin }, () => ({ token: "proxied" })),
  );
  await expect(
    new QueryClient({ defaultOptions: { queries: { retry: false } } }).fetchQuery(
      proxied.portalr.tenants("bob"),
    ),
  ).rejects.toThrow(/refused the read \(403\)/);
  const away = createQueries(
    createApi({ artifactr: "", reflexr: "", grantr: `${origin}/missing` }, () => ({ token: "x" })),
  );
  await expect(
    new QueryClient({ defaultOptions: { queries: { retry: false } } }).fetchQuery(
      away.portalr.tenants("bob"),
    ),
  ).rejects.toThrow(/refused the read \(404\)/);
});

test("the audit log is read from its end back, a page at a time, with its filter, until a page isn't full", async () => {
  const client = new QueryClient();
  const options = queries.grantr.audit("acme", {
    type: "member_added",
    actor_kind: "rule",
    actor: "triage",
    workspace: "ws_1",
  });
  const first = await client.fetchInfiniteQuery(options);
  expect(first.pages[0]).toHaveLength(AUDIT_PAGE);
  const request = seen.at(-1);
  expect(request?.url.pathname).toBe("/grantr/v1/tenants/acme/audit");
  expect(Object.fromEntries(request?.url.searchParams ?? [])).toEqual({
    last: String(AUDIT_PAGE),
    type: "member_added",
    actor_kind: "rule",
    actor: "triage",
    workspace: "ws_1",
  });
  // The next page is read before this one's oldest entry: 11 to 60, then 1 to 10.
  expect(options.getNextPageParam(first.pages[0] ?? [], first.pages, null, first.pageParams)).toBe(
    11,
  );
  const both = await client.fetchInfiniteQuery({ ...options, pages: 2 });
  expect(both.pages.map((page) => page.length)).toEqual([AUDIT_PAGE, 10]);
  expect(seen.at(-1)?.url.searchParams.get("before_seq")).toBe("11");
  expect(options.getNextPageParam(both.pages[1] ?? [], both.pages, 11, both.pageParams)).toBe(
    undefined,
  );
});

test("an audit read with no filter asks for every entry", async () => {
  await new QueryClient().fetchInfiniteQuery(queries.grantr.audit("acme", {}));
  expect([...(seen.at(-1)?.url.searchParams.keys() ?? [])]).toEqual(["last"]);
});

test("a workspace's grants and the tenant's are read apart", () => {
  expect(keys.grantr.grants("acme")).not.toEqual(keys.grantr.grants("acme", "ws_1"));
  expect(queries.grantr.grants("acme").queryKey).toEqual(keys.grantr.grants("acme"));
});
