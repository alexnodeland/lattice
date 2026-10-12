/**
 * TanStack Query's keys and query options for every read the UIs make, so that keys and their
 * invalidation live in one place. app and admin own the `QueryClient`; each read here is
 * `useQuery(queries.artifactr.threads(workspace))` there.
 *
 * Keys run from the surface to the workspace to the read, so invalidating a workspace's key
 * refetches everything read from it.
 */

import { queryOptions } from "@tanstack/react-query";
import { isKnown } from "./artifactr";
import type * as artifactrV1 from "./generated/artifactr.v1";
import type { components as Grantr } from "./generated/grantr.openapi";
import type { Api } from "./rest";

/** Every query's key. */
export const keys = {
  artifactr: {
    workspace: (workspace: string) => ["artifactr", workspace] as const,
    threads: (workspace: string) => ["artifactr", workspace, "threads"] as const,
    thread: (workspace: string, thread: string) =>
      ["artifactr", workspace, "threads", thread] as const,
    tail: (workspace: string, thread: string, last: number) =>
      ["artifactr", workspace, "threads", thread, "tail", last] as const,
    artifacts: (workspace: string) => ["artifactr", workspace, "artifacts"] as const,
    artifact: (workspace: string, artifact: string) =>
      ["artifactr", workspace, "artifacts", artifact] as const,
    proposals: (workspace: string) => ["artifactr", workspace, "proposals"] as const,
  },
  reflexr: {
    workspace: (workspace: string) => ["reflexr", workspace] as const,
    rules: (workspace: string) => ["reflexr", workspace, "rules"] as const,
    runs: (workspace: string) => ["reflexr", workspace, "runs"] as const,
  },
  grantr: {
    me: (tenant: string) => ["grantr", tenant, "me"] as const,
    checks: (tenant: string, checks: readonly Grantr["schemas"]["Check"][]) =>
      ["grantr", tenant, "checks", checks] as const,
  },
};

/** What a read returns, or the error it throws when the server refuses it. */
async function body<D>(
  response: Promise<{ data: D; error?: never } | { data?: never; error: unknown }>,
): Promise<D> {
  const result = await response;
  if (result.error !== undefined) {
    throw new Error(`the server refused the read: ${JSON.stringify(result.error)}`);
  }
  return result.data as D;
}

/** The query options of every read, over the given clients. */
export function createQueries(api: Api) {
  const workspace = (id: string) => ({ params: { path: { workspace_id: id } } });
  return {
    artifactr: {
      threads: (ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.threads(ws),
          queryFn: () =>
            body(api.artifactr.GET("/workspaces/{workspace_id}/threads", workspace(ws))),
        }),
      thread: (ws: string, thread: string) =>
        queryOptions({
          queryKey: keys.artifactr.thread(ws, thread),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/threads/{thread_id}", {
                params: { path: { workspace_id: ws, thread_id: thread } },
              }),
            ),
        }),
      /** A thread's latest events, which a stream then resumes after (artifactr's serving guide). */
      tail: (ws: string, thread: string, last: number) =>
        queryOptions({
          queryKey: keys.artifactr.tail(ws, thread, last),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/events", {
                params: { path: { workspace_id: ws }, query: { thread_id: [thread], last } },
              }),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      artifacts: (ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.artifacts(ws),
          queryFn: () =>
            body(api.artifactr.GET("/workspaces/{workspace_id}/artifacts", workspace(ws))),
        }),
      artifact: (ws: string, artifact: string) =>
        queryOptions({
          queryKey: keys.artifactr.artifact(ws, artifact),
          queryFn: () =>
            body(
              api.artifactr.GET("/workspaces/{workspace_id}/artifacts/{artifact_id}", {
                params: { path: { workspace_id: ws, artifact_id: artifact } },
              }),
            ),
        }),
      proposals: (ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.proposals(ws),
          queryFn: () =>
            body(api.artifactr.GET("/workspaces/{workspace_id}/proposals", workspace(ws))),
        }),
    },
    reflexr: {
      rules: (ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.rules(ws),
          queryFn: () => body(api.reflexr.GET("/workspaces/{workspace_id}/rules", workspace(ws))),
        }),
      runs: (ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.runs(ws),
          queryFn: () => body(api.reflexr.GET("/workspaces/{workspace_id}/runs", workspace(ws))),
        }),
    },
    grantr: {
      me: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.me(tenant),
          queryFn: () => body(api.grantr.GET("/grantr/v1/me")),
        }),
      /** Whether the caller may take each action, in the order asked (lattice RFC-0002). */
      checks: (tenant: string, checks: readonly Grantr["schemas"]["Check"][]) =>
        queryOptions({
          queryKey: keys.grantr.checks(tenant, checks),
          queryFn: () => body(api.grantr.POST("/grantr/v1/checks", { body: [...checks] })),
        }),
    },
  };
}

/** The keys whose reads an artifactr event makes stale, for `invalidateQueries`. */
export function staleAfter(workspace: string, envelope: artifactrV1.EventFrame) {
  const { event } = envelope;
  if (!isKnown(event)) {
    return [];
  }
  switch (event.type) {
    case "thread_created":
    case "thread_mode_changed":
    case "focus_changed":
      return [keys.artifactr.threads(workspace)];
    case "artifact_created":
    case "artifact_changed":
    case "artifact_archived":
      return [
        keys.artifactr.artifacts(workspace),
        keys.artifactr.artifact(workspace, event.artifact_id),
      ];
    case "proposal_created":
    case "proposal_resolved":
      return [keys.artifactr.proposals(workspace), keys.artifactr.artifacts(workspace)];
    default:
      return [];
  }
}
