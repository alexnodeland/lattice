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
import * as artifactr from "./artifactr";
import type * as artifactrV1 from "./generated/artifactr.v1";
import type { components as Grantr } from "./generated/grantr.openapi";
import type { components as Portalr } from "./generated/portalr.openapi";
import type * as reflexrV1 from "./generated/reflexr.v1";
import * as reflexr from "./reflexr";
import { type Api, named } from "./rest";

type Check = Grantr["schemas"]["Check"];
type Metric = Portalr["schemas"]["Metric"];

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
    rule: (tenant: string, ws: string, rule: string) =>
      [...keys.reflexr.workspace(tenant, ws), "rules", "detail", rule] as const,
    schedules: (tenant: string, ws: string) =>
      [...keys.reflexr.workspace(tenant, ws), "schedules", "list"] as const,
    runs: (tenant: string, ws: string) =>
      [...keys.reflexr.workspace(tenant, ws), "runs", "list"] as const,
  },
  grantr: {
    /** A person's tenants, by Supabase Auth's id for them. */
    memberships: (user: string) => ["grantr", "memberships", user] as const,
    /** Everything grantr answers in a tenant, which a change to access there makes stale. */
    tenant: (tenant: string) => ["grantr", tenant] as const,
    me: (tenant: string) => [...keys.grantr.tenant(tenant), "me"] as const,
    checks: (tenant: string, checks: readonly Check[]) =>
      [...keys.grantr.tenant(tenant), "checks", checks] as const,
    access: (tenant: string) => [...keys.grantr.tenant(tenant), "access"] as const,
    members: (tenant: string) => [...keys.grantr.access(tenant), "members"] as const,
    grants: (tenant: string, ws: string) => [...keys.grantr.access(tenant), "grants", ws] as const,
    restrictions: (tenant: string, ws: string) =>
      [...keys.grantr.access(tenant), "restrictions", ws] as const,
    /** Every grant in the tenant, on it and on everything in it, apart from a workspace's. */
    tenantGrants: (tenant: string) => [...keys.grantr.access(tenant), "tenant-grants"] as const,
    groups: (tenant: string) => [...keys.grantr.access(tenant), "groups"] as const,
    roles: (tenant: string) => [...keys.grantr.access(tenant), "roles"] as const,
    /** The deployment's catalog of roles, the same in every tenant: no change to access stales it. */
    catalog: () => ["grantr", "deployment", "catalog"] as const,
    keyring: (tenant: string) => [...keys.grantr.access(tenant), "keys"] as const,
  },
  portalr: {
    tenant: (tenant: string) => ["portalr", tenant] as const,
    spend: (tenant: string) => [...keys.portalr.tenant(tenant), "spend"] as const,
    scores: (tenant: string, window: TimeSpan) =>
      [...keys.portalr.tenant(tenant), "scores", window] as const,
    metrics: (tenant: string, metric: Metric, window: TimeSpan) =>
      [...keys.portalr.tenant(tenant), "metrics", metric, window] as const,
    /** The deployment's tenants, as the signed-in person, `user`, reads them: an operator's. */
    tenants: (user: string) => ["portalr", "deployment", "tenants", user] as const,
  },
};

/** A span of time to read, and for a series, the step between its points, in seconds. */
export interface TimeSpan {
  readonly start: string;
  readonly end: string;
  readonly step?: number;
}

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

/** Whether a refusal is grantr's or portalr's `forbidden`: the reader may not, not that it failed. */
function forbidden(error: unknown): boolean {
  if (!(error instanceof Refused) || error.status !== 403) {
    return false;
  }
  const { detail } = error;
  return (
    typeof detail === "object" &&
    detail !== null &&
    "detail" in detail &&
    typeof detail.detail === "object" &&
    detail.detail !== null &&
    "type" in detail.detail &&
    detail.detail.type === "forbidden"
  );
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
      /** One of the workspace's rules: a code rule, or an active stored one's current version. */
      rule: (tenant: string, ws: string, rule: string) =>
        queryOptions({
          queryKey: keys.reflexr.rule(tenant, ws, rule),
          queryFn: () =>
            body(
              api.reflexr.GET("/workspaces/{workspace_id}/rules/{rule}", {
                ...named(tenant),
                params: { path: { workspace_id: ws, rule } },
              }),
            ),
        }),
      /** When each schedule that ticks into the workspace last ticked, and ticks next. */
      schedules: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.schedules(tenant, ws),
          queryFn: () =>
            body(api.reflexr.GET("/workspaces/{workspace_id}/schedules", workspace(tenant, ws))),
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
      /** The tenant's members, for those who may add one (`grantr:add_member`). */
      members: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.members(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/members", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
      /** The grants on a workspace and on the threads and artifacts in it. */
      grants: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.grantr.grants(tenant, ws),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/grants", {
                ...named(tenant),
                params: { path: { tenant }, query: { workspace: ws } },
              }),
            ),
        }),
      /** The threads and artifacts restricted in a workspace. */
      restrictions: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.grantr.restrictions(tenant, ws),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/restrictions", {
                ...named(tenant),
                params: { path: { tenant }, query: { workspace: ws } },
              }),
            ),
        }),
      /** Every grant in the tenant, for those who may grant there (`grantr:grant`). */
      tenantGrants: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.tenantGrants(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/grants", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
      /** The tenant's custom roles (`grantr:define_role`). */
      roles: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.roles(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/roles", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
      /**
       * The built-in roles a tenant's admins grant, each with where, and what a custom role may
       * hold and where: the deployment's, which any signed-in caller may read (grantr ADR-0031).
       */
      catalog: () =>
        queryOptions({
          queryKey: keys.grantr.catalog(),
          queryFn: () => body(api.grantr.GET("/grantr/v1/catalog")),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /** The tenant's groups, by name, with their members (`grantr:manage_groups`). */
      groups: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.groups(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/groups", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
      /** The tenant's keys, by public id and principal, never their secrets (`grantr:issue_key`). */
      keyring: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.keyring(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/keys", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
    },
    portalr: {
      /** The tenant's spend against its budget, from its LiteLLM team. */
      spend: (tenant: string) =>
        queryOptions({
          queryKey: keys.portalr.spend(tenant),
          queryFn: () => body(api.portalr.GET("/portalr/v1/spend", named(tenant))),
        }),
      /** The tenant's feedback and evaluation scores in a window, from Langfuse. */
      scores: (tenant: string, window: TimeSpan) =>
        queryOptions({
          queryKey: keys.portalr.scores(tenant, window),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/scores", {
                ...named(tenant),
                params: { query: { start: window.start, end: window.end, limit: 1000 } },
              }),
            ),
        }),
      /** One of the tenant's series over a window, from Prometheus. */
      metrics: (tenant: string, metric: Metric, window: TimeSpan) =>
        queryOptions({
          queryKey: keys.portalr.metrics(tenant, metric, window),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/metrics", {
                ...named(tenant),
                params: {
                  query: {
                    metric,
                    start: window.start,
                    end: window.end,
                    ...(window.step !== undefined && { step: window.step }),
                    limit: 1000,
                  },
                },
              }),
            ),
        }),
      /**
       * Every tenant, with their spend, for an operator; null for anyone else, whom it's refused,
       * so the one read also says whether the reader is an operator.
       */
      tenants: (user: string) =>
        queryOptions({
          queryKey: keys.portalr.tenants(user),
          queryFn: async () => {
            try {
              return await body(api.portalr.GET("/portalr/v1/deployment/tenants"));
            } catch (error) {
              if (forbidden(error)) {
                return null;
              }
              throw error;
            }
          },
          // Who is an operator changes rarely: a minute, then it's read again.
          staleTime: 60_000,
        }),
    },
  };
}

/** The keys whose reads an event makes stale, for `invalidateQueries`. */
export const stale = {
  /** Every event artifactr's schema names is listed, so a new one fails the typecheck here. */
  artifactr(tenant: string, ws: string, envelope: artifactrV1.EventFrame) {
    const { event } = envelope;
    if (!artifactr.isKnown(event)) {
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

  /** reflexr's rule events make its rules stale, its run events its runs, and ticks its schedules. */
  reflexr(tenant: string, ws: string, envelope: reflexrV1.EventFrame) {
    const { event } = envelope;
    if (!reflexr.isKnown(event)) {
      return [];
    }
    switch (event.type) {
      case "reflexr:rule_fired":
      case "reflexr:rule_errored":
      case "reflexr:rule_reset":
      case "reflexr:rule_installed":
      case "reflexr:rule_archived":
        return [keys.reflexr.rules(tenant, ws), keys.reflexr.rule(tenant, ws, event.rule)];
      case "reflexr:run_started":
      case "reflexr:run_progressed":
      case "reflexr:run_retrying":
      case "reflexr:run_succeeded":
      case "reflexr:run_dead_lettered":
      case "reflexr:run_cancelled":
      case "reflexr:run_requeued":
      case "reflexr:run_skipped":
        return [keys.reflexr.runs(tenant, ws)];
      case "reflexr:tick":
        return [keys.reflexr.schedules(tenant, ws)];
      case "reflexr:feedback_given":
        return [];
      default:
        return event satisfies never;
    }
  },
};
