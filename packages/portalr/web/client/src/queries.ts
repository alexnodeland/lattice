/**
 * TanStack Query's keys and query options for every read the UIs make, so that keys and their
 * invalidation live in one place. app and admin own the `QueryClient`; each read here is
 * `useQuery(queries.artifactr.threads(workspace))` there.
 *
 * Keys run from the surface to the workspace to the resource, then split into its `list` and each
 * `detail`, so a list refetches without its details, and invalidating a workspace's key
 * refetches everything read from it.
 */

import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";
import * as artifactr from "./artifactr";
import type * as artifactrV1 from "./generated/artifactr.v1";
import type {
  components as Grantr,
  operations as GrantrOperations,
} from "./generated/grantr.openapi";
import type { components as Portalr } from "./generated/portalr.openapi";
import type * as reflexrV1 from "./generated/reflexr.v1";
import { reasons } from "./reasons";
import * as reflexr from "./reflexr";
import { type Api, named } from "./rest";
import { wholeTrace } from "./traces";

type Check = Grantr["schemas"]["Check"];
type AuditQuery = NonNullable<
  GrantrOperations["tenant_audit_grantr_v1_tenants__tenant__audit_get"]["parameters"]["query"]
>;

/**
 * Which of a tenant's audit entries a read keeps, as grantr's query takes it: one type of change,
 * or any, and one subject's changes, by its kind and id, and a rule's workspace, or anyone's
 * (grantr ADR-0030).
 */
export type AuditFilter = {
  readonly type?: Grantr["schemas"]["AuditType"] | undefined;
} & {
  readonly [K in "actor_kind" | "actor" | "workspace"]?: NonNullable<AuditQuery[K]> | undefined;
};

type Metric = Portalr["schemas"]["Metric"];

/** How many audit entries a page of the audit log reads. */
export const AUDIT_PAGE = 50;

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
    /** A workspace's grants, or with none named, every grant in the tenant, kept apart. */
    grants: (tenant: string, ws?: string) =>
      [...keys.grantr.access(tenant), "grants", ws ?? "~tenant"] as const,
    restrictions: (tenant: string, ws: string) =>
      [...keys.grantr.access(tenant), "restrictions", ws] as const,
    groups: (tenant: string) => [...keys.grantr.access(tenant), "groups"] as const,
    roles: (tenant: string) => [...keys.grantr.access(tenant), "roles"] as const,
    /**
     * The deployment's catalog of roles, the same in every tenant: under no tenant's key, so no
     * change to access stales it, and "~" keeps it from a tenant's name.
     */
    catalog: () => ["grantr", "~catalog"] as const,
    keyring: (tenant: string) => [...keys.grantr.access(tenant), "keys"] as const,
    /** A tenant's audit log, as a filter keeps it: a change to access there adds to it. */
    audit: (tenant: string, filter: AuditFilter) =>
      [...keys.grantr.tenant(tenant), "audit", filter] as const,
  },
  portalr: {
    tenant: (tenant: string) => ["portalr", tenant] as const,
    spend: (tenant: string) => [...keys.portalr.tenant(tenant), "spend"] as const,
    scores: (tenant: string, window: TimeSpan) =>
      [...keys.portalr.tenant(tenant), "scores", window] as const,
    metrics: (tenant: string, metric: Metric, window: TimeSpan) =>
      [...keys.portalr.tenant(tenant), "metrics", metric, window] as const,
    feedback: (tenant: string, window: TimeSpan, workspace: string | null) =>
      [...keys.portalr.tenant(tenant), "feedback", window, workspace] as const,
    usage: (tenant: string, window: TimeSpan, workspaces: readonly string[]) =>
      [...keys.portalr.tenant(tenant), "usage", window, workspaces] as const,
    traces: (tenant: string, window: TimeSpan, filter: TraceFilter) =>
      [...keys.portalr.tenant(tenant), "traces", "list", window, filter] as const,
    logs: (tenant: string, window: TimeSpan, filter: LogFilter) =>
      [...keys.portalr.tenant(tenant), "logs", "list", window, filter] as const,
    /** A log record's line, which is asked for, one record at a time. */
    logLine: (tenant: string, id: string) =>
      [...keys.portalr.tenant(tenant), "logs", "line", id] as const,
    /** A trace, and, apart, the same with one span's withheld attributes, which are asked for. */
    trace: (tenant: string, trace: string, span: string | null) =>
      [...keys.portalr.tenant(tenant), "traces", "detail", trace, span] as const,
    /** The deployment's tenants, as the signed-in person, `user`, reads them: an operator's. */
    tenants: (user: string) => ["portalr", "deployment", "tenants", user] as const,
    /** Deep links into the tools for a trace, which only an operator, `user`, reads. */
    links: (user: string, trace: string) =>
      ["portalr", "deployment", "links", user, trace] as const,
    /** An operator's links into the tools for the ids they gave, in Tools. */
    toolLinks: (user: string, ids: ToolIds) =>
      ["portalr", "deployment", "tool-links", user, ids] as const,
  },
};

/** What Tools makes links for: a trace's, a session's or a run's id, and a tenant, each optional. */
export interface ToolIds {
  readonly trace?: string | undefined;
  readonly session?: string | undefined;
  readonly run?: string | undefined;
  readonly tenant?: string | undefined;
}

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
    super(`the server refused the read (${status}): ${reasons(status, detail).join("; ")}`);
    this.status = status;
    this.detail = detail;
  }
}

/** Whether the server refused a read for what was asked: asking again would get the same. */
export const refusedOutright = (error: unknown) =>
  error instanceof Refused && error.status >= 400 && error.status < 500;

/** A long read is tried again once, unless the server refused it outright. */
const once = (count: number, error: unknown) => !refusedOutright(error) && count < 1;

/** What narrows a tenant's traces: a thread's, or a run's. */
export interface TraceFilter {
  readonly session?: string | undefined;
  readonly run?: string | undefined;
}

/** What narrows a tenant's logs: a thread's, or a run's. */
export interface LogFilter {
  readonly thread?: string | undefined;
  readonly run?: string | undefined;
}

/** The most log records one read asks for. */
export const LOGS_LIMIT = 1000;

/** The most traces one read asks for. */
export const TRACES_LIMIT = 100;

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
      /**
       * The grants on a workspace and on the threads and artifacts in it; or, with no workspace,
       * every grant in the tenant, for those who may grant there (`grantr:grant`).
       */
      grants: (tenant: string, ws?: string) =>
        queryOptions({
          queryKey: keys.grantr.grants(tenant, ws),
          queryFn: () =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/grants", {
                ...named(tenant),
                params: { path: { tenant }, query: ws === undefined ? {} : { workspace: ws } },
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
      /**
       * A tenant's audit log, as `filter` keeps it, from its end back, a page at a time: each
       * page is the last of the log before the previous page's oldest entry, oldest first, and a
       * page short of a full one is the first (`grantr:read_audit`, grantr ADR-0032).
       */
      audit: (tenant: string, filter: AuditFilter) =>
        infiniteQueryOptions({
          queryKey: keys.grantr.audit(tenant, filter),
          initialPageParam: null as number | null,
          queryFn: ({ pageParam }) =>
            body(
              api.grantr.GET("/grantr/v1/tenants/{tenant}/audit", {
                ...named(tenant),
                params: {
                  path: { tenant },
                  // openapi-fetch leaves out what is null.
                  query: {
                    last: AUDIT_PAGE,
                    before_seq: pageParam,
                    type: filter.type ? [filter.type] : null,
                    actor_kind: filter.actor_kind ?? null,
                    actor: filter.actor ?? null,
                    workspace: filter.workspace ?? null,
                  },
                },
              }),
            ),
          getNextPageParam: (page) => (page.length < AUDIT_PAGE ? undefined : page[0]?.seq),
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
          // Reading scores takes Langfuse two steps: kept a minute.
          staleTime: 60_000,
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
       * The tenant's feedback and evaluations over a window, or one workspace's, summed by day
       * from every score Langfuse holds in it (portalr ADR-0027).
       */
      feedback: (tenant: string, window: TimeSpan, workspace: string | null = null) =>
        queryOptions({
          queryKey: keys.portalr.feedback(tenant, window, workspace),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/feedback", {
                ...named(tenant),
                params: { query: { start: window.start, end: window.end, workspace } },
              }),
            ),
          // Summing a window reads Langfuse at length: kept a while, and tried again once.
          staleTime: 10 * 60_000,
          retry: once,
        }),
      /**
       * The tenant's spend per day over a window, from its LiteLLM team, and each named
       * workspace's, from its tag (portalr ADR-0028).
       */
      usage: (tenant: string, window: TimeSpan, workspaces: readonly string[] = []) =>
        queryOptions({
          queryKey: keys.portalr.usage(tenant, window, workspaces),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/usage", {
                ...named(tenant),
                params: {
                  query: { start: window.start, end: window.end, workspaces: [...workspaces] },
                },
              }),
            ),
          // Summing a window reads LiteLLM at length: kept a while, and tried again once.
          staleTime: 10 * 60_000,
          retry: once,
        }),
      /**
       * The tenant's newest traces in a window, up to `TRACES_LIMIT`, those of a thread or a run
       * if the filter names one, from Tempo (portalr ADR-0030).
       */
      traces: (tenant: string, window: TimeSpan, filter: TraceFilter = {}) =>
        queryOptions({
          queryKey: keys.portalr.traces(tenant, window, filter),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/traces", {
                ...named(tenant),
                params: {
                  query: {
                    start: window.start,
                    end: window.end,
                    limit: TRACES_LIMIT,
                    ...(filter.session && { session: filter.session }),
                    ...(filter.run && { run: filter.run }),
                  },
                },
              }),
            ),
          staleTime: 30_000,
        }),
      /**
       * The tenant's newest log records in a window of a day at most, up to `LOGS_LIMIT`, those
       * of a thread or a run if the filter names one, from Loki, without their lines
       * (portalr ADR-0031).
       */
      logs: (tenant: string, window: TimeSpan, filter: LogFilter = {}) =>
        queryOptions({
          queryKey: keys.portalr.logs(tenant, window, filter),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/logs", {
                ...named(tenant),
                params: {
                  query: {
                    start: window.start,
                    end: window.end,
                    limit: LOGS_LIMIT,
                    ...(filter.thread && { thread: filter.thread }),
                    ...(filter.run && { run: filter.run }),
                  },
                },
              }),
            ),
          staleTime: 30_000,
        }),
      /**
       * One log record by its id, with its line: asked for, read once, and let go: it isn't kept,
       * nor read again as the window regains focus, nor tried again if refused.
       */
      logLine: (tenant: string, id: string) =>
        queryOptions({
          queryKey: keys.portalr.logLine(tenant, id),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/logs/{record_id}", {
                ...named(tenant),
                params: { path: { record_id: id } },
              }),
            ),
          staleTime: 0,
          gcTime: 0,
          retry: false,
          refetchOnWindowFocus: false,
        }),
      /**
       * A trace by its id, whole however it is written: null if it isn't the tenant's, or isn't
       * there. Only its attributes known to be safe are in it. With `span`, one span's others are
       * too, which is a read of its own, for that span alone, and is not kept.
       */
      trace: (tenant: string, trace: string, span: string | null = null) => {
        const whole = wholeTrace(trace);
        return queryOptions({
          queryKey: keys.portalr.trace(tenant, whole, span),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/traces/{trace_id}", {
                ...named(tenant),
                params: {
                  path: { trace_id: whole },
                  query: span === null ? {} : { content: true, span },
                },
              }),
            ),
          // A trace is written once it ends: what is read of it stays good for a while. What a
          // span withheld is read when asked, shown, and let go: it isn't kept in the page's cache.
          staleTime: span === null ? 5 * 60_000 : 0,
          gcTime: span === null ? 5 * 60_000 : 0,
          // A span's withheld attributes are read once, when it asks: not again as the window
          // regains focus, and, if refused, not tried three times before it says so.
          ...(span !== null && { retry: false, refetchOnWindowFocus: false }),
        });
      },
      /** An operator's deep links into Langfuse and Grafana for a trace. */
      links: (user: string, trace: string) =>
        queryOptions({
          queryKey: keys.portalr.links(user, trace),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/deployment/links", {
                params: { query: { trace_id: trace } },
              }),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /**
       * An operator's links into Langfuse and Grafana for the ids given. Each read is one that the
       * server records, so it is never kept: not fresh, not cached once nothing shows it, and not
       * read again on focus or by a retry.
       */
      toolLinks: (user: string, ids: ToolIds) =>
        queryOptions({
          queryKey: keys.portalr.toolLinks(user, ids),
          queryFn: () =>
            body(
              api.portalr.GET("/portalr/v1/deployment/links", {
                params: {
                  query: {
                    trace_id: ids.trace ?? null,
                    session_id: ids.session ?? null,
                    run_id: ids.run ?? null,
                    tenant_id: ids.tenant ?? null,
                  },
                },
              }),
            ),
          staleTime: 0,
          gcTime: 0,
          retry: false,
          refetchOnWindowFocus: false,
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
