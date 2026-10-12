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

/** Every query's key. */
export const keys = {
  artifactr: {
    workspaces: () => ["artifactr", "workspaces"] as const,
    workspace: (ws: string) => ["artifactr", "workspace", ws] as const,
    threads: (ws: string) => ["artifactr", "workspace", ws, "threads", "list"] as const,
    thread: (ws: string, thread: string) =>
      ["artifactr", "workspace", ws, "threads", "detail", thread] as const,
    tail: (ws: string, thread: string, last: number) =>
      ["artifactr", "workspace", ws, "threads", "tail", thread, last] as const,
    artifacts: (ws: string) => ["artifactr", "workspace", ws, "artifacts", "list"] as const,
    artifact: (ws: string, artifact: string) =>
      ["artifactr", "workspace", ws, "artifacts", "detail", artifact] as const,
    proposals: (ws: string) => ["artifactr", "workspace", ws, "proposals", "list"] as const,
  },
  reflexr: {
    workspace: (ws: string) => ["reflexr", "workspace", ws] as const,
    rules: (ws: string) => ["reflexr", "workspace", ws, "rules", "list"] as const,
    runs: (ws: string) => ["reflexr", "workspace", ws, "runs", "list"] as const,
  },
  grantr: {
    memberships: () => ["grantr", "memberships"] as const,
    me: (tenant: string) => ["grantr", tenant, "me"] as const,
    checks: (tenant: string, checks: readonly Check[]) =>
      ["grantr", tenant, "checks", checks] as const,
  },
};

/** What a read returns, or the error it throws when the server refuses it. */
async function body<D>(response: Promise<{ data?: D; error?: unknown }>): Promise<D> {
  const { data, error } = await response;
  if (data === undefined) {
    throw new Error(`the server refused the read: ${JSON.stringify(error)}`);
  }
  return data;
}

/** The query options of every read, over the given clients. */
export function createQueries(api: Api) {
  const workspace = (id: string) => ({ params: { path: { workspace_id: id } } });
  return {
    artifactr: {
      /** The tenant's workspaces. */
      workspaces: () =>
        queryOptions({
          queryKey: keys.artifactr.workspaces(),
          queryFn: () => body(api.artifactr.GET("/workspaces")),
        }),
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
      /** Every tenant the caller is a member of; asked while the session names no tenant. */
      memberships: () =>
        queryOptions({
          queryKey: keys.grantr.memberships(),
          queryFn: async () => {
            const me = await body(api.grantr.GET("/grantr/v1/me"));
            if (!("memberships" in me)) {
              throw new Error("grantr answered for one tenant: the session names one");
            }
            return me.memberships;
          },
        }),
      /** The caller in the session's tenant: their roles, and the workspaces they can open. */
      me: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.me(tenant),
          queryFn: async () => {
            const me = await body(api.grantr.GET("/grantr/v1/me"));
            if ("memberships" in me) {
              throw new Error("grantr answered for every tenant: the session names none");
            }
            return me;
          },
        }),
      /** Whether the caller may take each action, in the order asked (lattice RFC-0002). */
      checks: (tenant: string, checks: readonly Check[]) =>
        queryOptions({
          queryKey: keys.grantr.checks(tenant, checks),
          queryFn: () => body(api.grantr.POST("/grantr/v1/checks", { body: [...checks] })),
        }),
    },
  };
}

/** The keys whose reads an event makes stale, for `invalidateQueries`. */
export const stale = {
  /** Every event artifactr's schema names is listed, so a new one fails the typecheck here. */
  artifactr(ws: string, envelope: artifactrV1.EventFrame) {
    const { event } = envelope;
    if (!isKnown(event)) {
      return [];
    }
    switch (event.type) {
      case "thread_created":
        return [keys.artifactr.threads(ws)];
      case "thread_mode_changed":
      case "focus_changed":
        return [keys.artifactr.threads(ws), keys.artifactr.thread(ws, event.thread_id)];
      case "artifact_created":
      case "artifact_changed":
      case "artifact_archived":
        return [keys.artifactr.artifacts(ws), keys.artifactr.artifact(ws, event.artifact_id)];
      case "proposal_created":
        return [keys.artifactr.proposals(ws)];
      case "proposal_resolved":
        return [
          keys.artifactr.proposals(ws),
          keys.artifactr.artifacts(ws),
          keys.artifactr.artifact(ws, event.artifact_id),
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
  reflexr(ws: string, envelope: reflexrV1.EventFrame) {
    const { type } = envelope.event;
    if (type.startsWith("reflexr:rule_")) {
      return [keys.reflexr.rules(ws)];
    }
    if (type.startsWith("reflexr:run_")) {
      return [keys.reflexr.runs(ws)];
    }
    return [];
  },
};
