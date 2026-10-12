/**
 * TanStack Query's keys and query options for every read the UIs make, so that keys and their
 * invalidation live in one place. app and admin own the `QueryClient`; each read here is
 * `useQuery(queries.artifactr.threads(workspace))` there.
 *
 * Keys run from the surface to the workspace to the resource, then split into its `list` and each
 * `detail`, so a list refetches without its details, and invalidating a workspace's key
 * refetches everything read from it.
 */

import { queryOptions } from "@tanstack/react-query";
import { isKnown } from "./artifactr";
import type * as artifactrV1 from "./generated/artifactr.v1";
import type { components as Grantr } from "./generated/grantr.openapi";
import type * as reflexrV1 from "./generated/reflexr.v1";
import type { Api } from "./rest";

type Check = Grantr["schemas"]["Check"];

/** Every query's key: each names its tenant, so two tenants' reads never share a cache entry. */
export const keys = {
  artifactr: {
    workspaces: (tenant: string) => ["artifactr", tenant, "workspaces"] as const,
    workspace: (tenant: string, ws: string) => ["artifactr", tenant, "workspace", ws] as const,
    threads: (tenant: string, ws: string) =>
      [...keys.artifactr.workspace(tenant, ws), "threads", "list"] as const,
    thread: (tenant: string, ws: string, thread: string) =>
      [...keys.artifactr.workspace(tenant, ws), "threads", "detail", thread] as const,
    tail: (tenant: string, ws: string, thread: string, last: number) =>
      [...keys.artifactr.workspace(tenant, ws), "threads", "tail", thread, last] as const,
    artifacts: (tenant: string, ws: string) =>
      [...keys.artifactr.workspace(tenant, ws), "artifacts", "list"] as const,
    artifact: (tenant: string, ws: string, artifact: string) =>
      [...keys.artifactr.workspace(tenant, ws), "artifacts", "detail", artifact] as const,
    revisions: (tenant: string, ws: string, artifact: string) =>
      [...keys.artifactr.artifact(tenant, ws, artifact), "revisions"] as const,
    proposals: (tenant: string, ws: string) =>
      [...keys.artifactr.workspace(tenant, ws), "proposals", "list"] as const,
  },
  reflexr: {
    workspace: (tenant: string, ws: string) => ["reflexr", tenant, "workspace", ws] as const,
    rules: (tenant: string, ws: string) =>
      [...keys.reflexr.workspace(tenant, ws), "rules", "list"] as const,
    runs: (tenant: string, ws: string) =>
      [...keys.reflexr.workspace(tenant, ws), "runs", "list"] as const,
  },
  grantr: {
    /** A person's tenants, by Supabase Auth's id for them. */
    memberships: (user: string) => ["grantr", "memberships", user] as const,
    me: (tenant: string) => ["grantr", tenant, "me"] as const,
    checks: (tenant: string, checks: readonly Check[]) =>
      ["grantr", tenant, "checks", checks] as const,
  },
};

/** What a read returns, or the error it throws when the server refuses it. */
async function body<D>(
  response: Promise<{ data?: D; error?: unknown; response: Response }>,
): Promise<D> {
  const { data, error, response: answered } = await response;
  if (data === undefined) {
    throw new Refused(answered.status, error);
  }
  return data;
}

/** The server refused a read: 401 when no one is signed in, 403 when they may not. */
export class Refused extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`the server refused the read (${status}): ${JSON.stringify(detail)}`);
    this.status = status;
    this.detail = detail;
  }
}

/** The headers that name a read's tenant. */
const named = (tenant: string) => ({ headers: { "X-Tenant": tenant } });

/** The query options of every read, over the given clients. */
export function createQueries(api: Api) {
  const workspace = (tenant: string, id: string) => ({
    ...named(tenant),
    params: { path: { workspace_id: id } },
  });
  return {
    artifactr: {
      /** The tenant's workspaces. */
      workspaces: (tenant: string) =>
        queryOptions({
          queryKey: keys.artifactr.workspaces(tenant),
          queryFn: () => body(api.artifactr.GET("/workspaces", named(tenant))),
        }),
      threads: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.threads(tenant, ws),
          queryFn: () =>
            body(api.artifactr.GET("/workspaces/{workspace_id}/threads", workspace(tenant, ws))),
        }),
      thread: (tenant: string, ws: string, thread: string) =>
        queryOptions({
          queryKey: keys.artifactr.thread(tenant, ws, thread),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/threads/{thread_id}", {
                ...named(tenant),
                params: { path: { workspace_id: ws, thread_id: thread } },
              }),
            ),
        }),
      /** A thread's latest events, which a stream then resumes after (artifactr's serving guide). */
      tail: (tenant: string, ws: string, thread: string, last: number) =>
        queryOptions({
          queryKey: keys.artifactr.tail(tenant, ws, thread, last),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/events", {
                ...named(tenant),
                params: { path: { workspace_id: ws }, query: { thread_id: [thread], last } },
              }),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      artifacts: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.artifacts(tenant, ws),
          queryFn: () =>
            body(api.artifactr.GET("/workspaces/{workspace_id}/artifacts", workspace(tenant, ws))),
        }),
      artifact: (tenant: string, ws: string, artifact: string) =>
        queryOptions({
          queryKey: keys.artifactr.artifact(tenant, ws, artifact),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/artifacts/{artifact_id}", {
                ...named(tenant),
                params: { path: { workspace_id: ws, artifact_id: artifact } },
              }),
            ),
        }),
      /** An artifact's versions, oldest first, each with its whole data: the last is now. */
      revisions: (tenant: string, ws: string, artifact: string) =>
        queryOptions({
          queryKey: keys.artifactr.revisions(tenant, ws, artifact),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/artifacts/{artifact_id}/revisions", {
                ...named(tenant),
                params: { path: { workspace_id: ws, artifact_id: artifact } },
              }),
            ),
        }),
      proposals: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.proposals(tenant, ws),
          queryFn: () =>
            body(api.artifactr.GET("/workspaces/{workspace_id}/proposals", workspace(tenant, ws))),
        }),
    },
    reflexr: {
      rules: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.rules(tenant, ws),
          queryFn: () =>
            body(api.reflexr.GET("/workspaces/{workspace_id}/rules", workspace(tenant, ws))),
        }),
      runs: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.runs(tenant, ws),
          queryFn: () =>
            body(api.reflexr.GET("/workspaces/{workspace_id}/runs", workspace(tenant, ws))),
        }),
    },
    grantr: {
      /** Every tenant the signed-in person, `user`, is a member of: asked in no tenant. */
      memberships: (user: string) =>
        queryOptions({
          queryKey: keys.grantr.memberships(user),
          queryFn: async () => {
            const me = await body(api.grantr.GET("/grantr/v1/me"));
            if (!("memberships" in me)) {
              throw new Error("grantr answered for one tenant, though the read named none");
            }
            return me.memberships;
          },
        }),
      /** The caller in a tenant: their roles, and the workspaces they can open. */
      me: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.me(tenant),
          queryFn: async () => {
            const me = await body(
              api.grantr.GET("/grantr/v1/me", { params: { header: { "X-Tenant": tenant } } }),
            );
            if ("memberships" in me) {
              throw new Error("grantr answered for every tenant, though the read named one");
            }
            return me;
          },
        }),
      /** Whether the caller may take each action, in the order asked (lattice RFC-0002). */
      checks: (tenant: string, checks: readonly Check[]) =>
        queryOptions({
          queryKey: keys.grantr.checks(tenant, checks),
          queryFn: () =>
            body(
              api.grantr.POST("/grantr/v1/checks", {
                params: { header: { "X-Tenant": tenant } },
                body: [...checks],
              }),
            ),
        }),
    },
  };
}

/** The keys whose reads an event makes stale, for `invalidateQueries`. */
export const stale = {
  /** Every event artifactr's schema names is listed, so a new one fails the typecheck here. */
  artifactr(tenant: string, ws: string, envelope: artifactrV1.EventFrame) {
    const { event } = envelope;
    if (!isKnown(event)) {
      return [];
    }
    switch (event.type) {
      case "thread_created":
        return [keys.artifactr.threads(tenant, ws)];
      case "thread_mode_changed":
      case "focus_changed":
        return [
          keys.artifactr.threads(tenant, ws),
          keys.artifactr.thread(tenant, ws, event.thread_id),
        ];
      case "artifact_created":
      case "artifact_changed":
      case "artifact_archived":
        return [
          keys.artifactr.artifacts(tenant, ws),
          keys.artifactr.artifact(tenant, ws, event.artifact_id),
        ];
      case "proposal_created":
        return [keys.artifactr.proposals(tenant, ws)];
      case "proposal_resolved":
        return [
          keys.artifactr.proposals(tenant, ws),
          keys.artifactr.artifacts(tenant, ws),
          keys.artifactr.artifact(tenant, ws, event.artifact_id),
        ];
      // The store holds what these change; no read goes stale.
      case "message_posted":
      case "run_started":
      case "tool_called":
      case "tool_returned":
      case "run_paused":
      case "deferred_answered":
      case "run_ended":
      case "feedback_given":
      case "app_event":
        return [];
      default:
        return event satisfies never;
    }
  },

  /** reflexr's rule events make its rules stale, and its run events its runs. */
  reflexr(tenant: string, ws: string, envelope: reflexrV1.EventFrame) {
    const { type } = envelope.event;
    if (type.startsWith("reflexr:rule_")) {
      return [keys.reflexr.rules(tenant, ws)];
    }
    if (type.startsWith("reflexr:run_")) {
      return [keys.reflexr.runs(tenant, ws)];
    }
    return [];
  },
};
