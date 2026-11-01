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
import { pngDataUrl } from "./files";
import type * as artifactrV1 from "./generated/artifactr.v1";
import type {
  components as Grantr,
  operations as GrantrOperations,
} from "./generated/grantr.openapi";
import type { components as Portalr } from "./generated/portalr.openapi";
import type * as reflexrV1 from "./generated/reflexr.v1";
import type { components as Relayr } from "./generated/relayr.openapi";
import { refusalSaid, sentenceOf } from "./reasons";
import * as reflexr from "./reflexr";
import { type Api, named } from "./rest";
import type { Result } from "./stream";
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

/** What a workspace's runs filed in its tracker, as relayr answers. */
export type Filed = Relayr["schemas"]["Filed"];

/** One item a workspace's runs filed, with its link and the chains that wrote to it. */
export type FiledItem = Relayr["schemas"]["FiledItem"];

/** How the tracker connector is doing in a workspace, as relayr answers. */
export type Following = Relayr["schemas"]["Following"];

/** The most people one request for their emails names, as the server takes them. */
export const PEOPLE_MAX = 100;

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
  /**
   * Native files. A file's status, with who has it, is under its artifact's key, so a change to
   * the file makes it stale. What a version or a proposal holds never changes, so its words and
   * pages are under keys of their own, which no event makes stale: a change refetches none.
   */
  files: {
    status: (tenant: string, ws: string, artifact: string) =>
      [...keys.artifactr.artifact(tenant, ws, artifact), "file"] as const,
    version: (tenant: string, ws: string, artifact: string, version: number) =>
      ["files", tenant, ws, "version", artifact, version] as const,
    proposal: (tenant: string, ws: string, proposal: string) =>
      ["files", tenant, ws, "proposal", proposal] as const,
    /** What may be uploaded, under the tenant's integrations: switching an app makes it stale. */
    uploads: (tenant: string, ws: string) =>
      [...keys.grantr.integrations(tenant), "uploads", ws] as const,
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
  relayr: {
    workspace: (tenant: string, ws: string) => ["relayr", tenant, "workspace", ws] as const,
    /** The items a workspace's runs filed in its tracker, which a run's end makes stale. */
    filed: (tenant: string, ws: string) => [...keys.relayr.workspace(tenant, ws), "filed"] as const,
    /** How the tracker connector is doing in a workspace. */
    following: (tenant: string, ws: string) =>
      [...keys.relayr.workspace(tenant, ws), "following"] as const,
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
    /** Every approval read in a tenant, which an answer there makes stale. */
    approvals: (tenant: string) => [...keys.grantr.tenant(tenant), "approvals"] as const,
    /** The approvals pending in a tenant that the reader may answer. */
    approvalList: (tenant: string) => [...keys.grantr.approvals(tenant), "list"] as const,
    /** One approval, as it stands, for one who may answer it or the person it was asked for. */
    approval: (tenant: string, id: string) =>
      [...keys.grantr.approvals(tenant), "detail", id] as const,
    /** The deployment's audit log, as the signed-in operator, `user`, reads it. */
    deploymentAudit: (user: string) => ["grantr", "deployment", "audit", user] as const,
    /** A tenant's audit log, as a filter keeps it: a change to access there adds to it. */
    audit: (tenant: string, filter: AuditFilter) =>
      [...keys.grantr.tenant(tenant), "audit", filter] as const,
    /**
     * Everything read of a tenant's integrations, which a setting anywhere in it makes stale: a
     * tenant's setting changes what each of its workspaces gets.
     */
    integrations: (tenant: string) => [...keys.grantr.tenant(tenant), "integrations"] as const,
    /** Each integration as it is set on the tenant, or with a workspace named, in that workspace. */
    integrationStates: (tenant: string, ws?: string) =>
      [...keys.grantr.integrations(tenant), "states", ws ?? "~tenant"] as const,
    /** Whether each integration is on in a workspace, as its members read it. */
    enabledIntegrations: (tenant: string, ws: string) =>
      [...keys.grantr.integrations(tenant), "enabled", ws] as const,
    /**
     * Everything read of a tenant's settings, which a change anywhere in it makes stale: a
     * tenant's value is the ceiling of each of its workspaces'.
     */
    settings: (tenant: string) => [...keys.grantr.tenant(tenant), "settings"] as const,
    /** Each setting as it is narrowed on the tenant, or with a workspace named, in it. */
    settingStates: (tenant: string, ws?: string) =>
      [...keys.grantr.settings(tenant), "states", ws ?? "~tenant"] as const,
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
    adoption: (tenant: string, window: TimeSpan) =>
      [...keys.portalr.tenant(tenant), "adoption", window] as const,
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
    /**
     * The emails of some people, as the reader may see them in a tenant, or an operator anywhere
     * with none. The ids are sorted and without repeats, so one set is one entry.
     */
    people: (tenant: string | null, ids: readonly string[]) =>
      ["portalr", tenant ?? "~deployment", "people", ids] as const,
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
    throw await refusal(answered, error);
  }
  return data;
}

/**
 * The server's refusal of a read: its status, its detail, the seconds it said to wait, and what a
 * reader is told of it, where values aren't valid with where they are.
 */
export async function refusal(answered: Response, detail: unknown): Promise<Refused> {
  const wait = Number.parseInt(answered.headers.get("retry-after") ?? "", 10);
  const said = await refusalSaid(answered.status, detail);
  return new Refused(answered.status, detail, Number.isNaN(wait) ? null : wait, said);
}

/** A read's answer, or null where the server has none to give (`409`, nothing to read). */
async function words<T>(
  response: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T | null> {
  try {
    return await body(response);
  } catch (error) {
    if (error instanceof Refused && error.status === 409) {
      return null;
    }
    throw error;
  }
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

/**
 * The server refused a read: 401 when no one is signed in, 403 when they may not, 429 when it is
 * busy or paced, with the seconds it said to wait (`Retry-After`), if it said.
 */
export class Refused extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly retryAfter: number | null;
  /** What a reader is told of it: the kit's sentence, never the server's words (ADR-0070). */
  readonly said: string;

  constructor(
    status: number,
    detail: unknown,
    retryAfter: number | null = null,
    said = sentenceOf(status, detail),
  ) {
    super(`the server refused the read (${status}): ${said}`);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
    this.said = said;
  }
}

/**
 * Whether the server refused a read for what was asked: asking again would get the same. A 429
 * is not: it is asked again once the server's wait has passed.
 */
export const refusedOutright = (error: unknown) =>
  error instanceof Refused && error.status >= 400 && error.status < 500 && error.status !== 429;

/** How long to wait before a read is tried again: the server's `Retry-After`, or a backoff. */
export const retryDelay = (count: number, error: unknown) => {
  // The server's wait, at least none and at most five minutes, or a backoff of our own.
  const wait =
    error instanceof Refused && error.retryAfter !== null
      ? Math.min(Math.max(error.retryAfter, 0), 300) * 1000
      : Math.min(1000 * 2 ** count, 30_000);
  // Up to a fifth more, at random, so the reads a busy server refused together don't all come
  // back at the same moment.
  return wait + Math.random() * (wait / 5);
};

/** A long read is tried again once, unless the server refused it outright. */
const once = (count: number, error: unknown) => !refusedOutright(error) && count < 1;

/** What narrows a tenant's traces: a thread's, a run's, or an analytics session's. */
export interface TraceFilter {
  readonly session?: string | undefined;
  readonly run?: string | undefined;
  readonly analytics_session?: string | undefined;
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
          queryFn: () =>
            body(api.artifactr.GET("artifactr.list_workspaces", "/workspaces", named(tenant))),
        }),
      threads: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.threads(tenant, ws),
          queryFn: () =>
            body(
              api.artifactr.GET(
                "artifactr.list_threads",
                "/workspaces/{workspace_id}/threads",
                workspace(tenant, ws),
              ),
            ),
        }),
      thread: (tenant: string, ws: string, thread: string) =>
        queryOptions({
          queryKey: keys.artifactr.thread(tenant, ws, thread),
          queryFn: () =>
            body(
              api.artifactr.GET(
                "artifactr.read_thread",
                "/workspaces/{workspace_id}/threads/{thread_id}",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, thread_id: thread } },
                },
              ),
            ),
        }),
      /** A thread's latest events, which a stream then resumes after (artifactr's serving guide). */
      tail: (tenant: string, ws: string, thread: string, last: number) =>
        queryOptions({
          queryKey: keys.artifactr.tail(tenant, ws, thread, last),
          queryFn: () =>
            body(
              api.artifactr.GET("artifactr.read_events", "/workspaces/{workspace_id}/events", {
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
            body(
              api.artifactr.GET(
                "artifactr.list_artifacts",
                "/workspaces/{workspace_id}/artifacts",
                workspace(tenant, ws),
              ),
            ),
        }),
      artifact: (tenant: string, ws: string, artifact: string) =>
        queryOptions({
          queryKey: keys.artifactr.artifact(tenant, ws, artifact),
          queryFn: () =>
            body(
              api.artifactr.GET(
                "artifactr.read_artifact",
                "/workspaces/{workspace_id}/artifacts/{artifact_id}",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, artifact_id: artifact } },
                },
              ),
            ),
        }),
      /** An artifact's versions, oldest first, each with its whole data: the last is now. */
      revisions: (tenant: string, ws: string, artifact: string) =>
        queryOptions({
          queryKey: keys.artifactr.revisions(tenant, ws, artifact),
          queryFn: () =>
            body(
              api.artifactr.GET(
                "artifactr.list_revisions",
                "/workspaces/{workspace_id}/artifacts/{artifact_id}/revisions",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, artifact_id: artifact } },
                },
              ),
            ),
        }),
      proposals: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.artifactr.proposals(tenant, ws),
          queryFn: () =>
            body(
              api.artifactr.GET(
                "artifactr.list_proposals",
                "/workspaces/{workspace_id}/proposals",
                workspace(tenant, ws),
              ),
            ),
        }),
    },
    files: {
      /**
       * A native file's status: its head, who has it and until when, and whether it can be checked
       * out. A lease has no event, so it is read again every half minute, and every two seconds
       * while an agent's edit holds the file, for seconds; once refused, not again until asked.
       */
      status: (tenant: string, ws: string, artifact: string) =>
        queryOptions({
          queryKey: keys.files.status(tenant, ws, artifact),
          queryFn: () =>
            body(
              api.files.GET(
                "artifactr.read_file",
                "/workspaces/{workspace_id}/files/{artifact_id}",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, artifact_id: artifact } },
                },
              ),
            ),
          refetchInterval: (query) => {
            if (query.state.status === "error") {
              return false; // refused, as where native files' routes aren't served: not again
            }
            return query.state.data?.lease?.checked_out_by === null ? 2_000 : 30_000;
          },
        }),
      /**
       * What the reader may upload in a workspace: whether at all, how large, and each native
       * kind with its app's switch, read again every half minute, as the kill switch reads the
       * workspace's integrations; once refused, not again until asked.
       */
      uploads: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.files.uploads(tenant, ws),
          queryFn: () =>
            body(api.files.GET(null, "/workspaces/{workspace_id}/uploads", workspace(tenant, ws))),
          refetchInterval: (query) => (query.state.status === "error" ? false : 30_000),
        }),
      /**
       * A version's bytes, for the app to save, as `fetchQuery` reads it: never kept, since a file
       * can be megabytes and is saved once.
       */
      content: (tenant: string, ws: string, artifact: string, version: number) =>
        queryOptions({
          queryKey: [...keys.files.version(tenant, ws, artifact, version), "content"],
          queryFn: () =>
            body(
              api.files.GET(
                "artifactr.read_file",
                "/workspaces/{workspace_id}/files/{artifact_id}/versions/{version}/content",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, artifact_id: artifact, version } },
                  parseAs: "blob",
                },
              ),
            ),
          gcTime: 0,
        }),
      /** A version's words, or null where it has none to read (`409`). */
      text: (tenant: string, ws: string, artifact: string, version: number) =>
        queryOptions({
          queryKey: [...keys.files.version(tenant, ws, artifact, version), "text"],
          queryFn: () =>
            words(
              api.files.GET(
                "artifactr.read_file",
                "/workspaces/{workspace_id}/files/{artifact_id}/versions/{version}/text",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, artifact_id: artifact, version } },
                  parseAs: "text",
                },
              ),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /** One page of a version, rendered, as a `data:` URL: the UIs' policy has no `blob:`. */
      page: (tenant: string, ws: string, artifact: string, version: number, page: number) =>
        queryOptions({
          queryKey: [...keys.files.version(tenant, ws, artifact, version), "page", page],
          queryFn: async () =>
            pngDataUrl(
              await body(
                api.files.GET(
                  "artifactr.read_file",
                  "/workspaces/{workspace_id}/files/{artifact_id}/versions/{version}/pages/{page}",
                  {
                    ...named(tenant),
                    params: { path: { workspace_id: ws, artifact_id: artifact, version, page } },
                    parseAs: "arrayBuffer",
                  },
                ),
              ),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /** The words a proposal would give a native file, or null where it names none. */
      proposedText: (tenant: string, ws: string, proposal: string) =>
        queryOptions({
          queryKey: [...keys.files.proposal(tenant, ws, proposal), "text"],
          queryFn: () =>
            words(
              api.files.GET(
                "artifactr.list_proposals",
                "/workspaces/{workspace_id}/proposals/{proposal_id}/text",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, proposal_id: proposal } },
                  parseAs: "text",
                },
              ),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /**
       * What an agent's proposal on a native file does, in words: a line, and each command, or
       * null for one made by no commands, as a person's check-in kept as a proposal.
       */
      proposedCommands: (tenant: string, ws: string, proposal: string) =>
        queryOptions({
          queryKey: [...keys.files.proposal(tenant, ws, proposal), "commands"],
          queryFn: () =>
            words(
              api.files.GET(
                "artifactr.list_proposals",
                "/workspaces/{workspace_id}/proposals/{proposal_id}/commands",
                {
                  ...named(tenant),
                  params: { path: { workspace_id: ws, proposal_id: proposal } },
                },
              ),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /** One page of what a proposal would make of a native file, as a `data:` URL. */
      proposedPage: (tenant: string, ws: string, proposal: string, page: number) =>
        queryOptions({
          queryKey: [...keys.files.proposal(tenant, ws, proposal), "page", page],
          queryFn: async () =>
            pngDataUrl(
              await body(
                api.files.GET(
                  "artifactr.list_proposals",
                  "/workspaces/{workspace_id}/proposals/{proposal_id}/pages/{page}",
                  {
                    ...named(tenant),
                    params: { path: { workspace_id: ws, proposal_id: proposal, page } },
                    parseAs: "arrayBuffer",
                  },
                ),
              ),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
    },
    reflexr: {
      rules: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.rules(tenant, ws),
          queryFn: () =>
            body(
              api.reflexr.GET(
                "reflexr.rule_status",
                "/workspaces/{workspace_id}/rules",
                workspace(tenant, ws),
              ),
            ),
        }),
      /** One of the workspace's rules: a code rule, or an active stored one's current version. */
      rule: (tenant: string, ws: string, rule: string) =>
        queryOptions({
          queryKey: keys.reflexr.rule(tenant, ws, rule),
          queryFn: () =>
            body(
              api.reflexr.GET("reflexr.get_rule", "/workspaces/{workspace_id}/rules/{rule}", {
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
            body(
              api.reflexr.GET(
                "reflexr.schedule_status",
                "/workspaces/{workspace_id}/schedules",
                workspace(tenant, ws),
              ),
            ),
        }),
      runs: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.reflexr.runs(tenant, ws),
          queryFn: () =>
            body(
              api.reflexr.GET(
                "reflexr.list_runs",
                "/workspaces/{workspace_id}/runs",
                workspace(tenant, ws),
              ),
            ),
        }),
    },
    relayr: {
      /**
       * The items a workspace's runs filed in its tracker, each with its link and the chains that
       * wrote to it; none where the application has no tracker.
       */
      filed: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.relayr.filed(tenant, ws),
          queryFn: (): Promise<Filed | null> =>
            api.relayr === null
              ? Promise.resolve(null)
              : body(
                  api.relayr.GET(
                    "relayr.list_filed_items",
                    "/relayr/v1/workspaces/{workspace_id}/tracker/items",
                    workspace(tenant, ws),
                  ),
                ),
        }),
      /** How the tracker connector is doing in a workspace; none where there is no tracker. */
      following: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.relayr.following(tenant, ws),
          queryFn: (): Promise<Following | null> =>
            api.relayr === null
              ? Promise.resolve(null)
              : body(
                  api.relayr.GET(
                    "relayr.tracker_status",
                    "/relayr/v1/workspaces/{workspace_id}/tracker",
                    workspace(tenant, ws),
                  ),
                ),
        }),
    },
    grantr: {
      /** Every tenant the signed-in person, `user`, is a member of: asked in no tenant. */
      memberships: (user: string) =>
        queryOptions({
          queryKey: keys.grantr.memberships(user),
          queryFn: async () => {
            const me = await body(api.grantr.GET(null, "/grantr/v1/me"));
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
              api.grantr.GET(null, "/grantr/v1/me", { params: { header: { "X-Tenant": tenant } } }),
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
              api.grantr.POST(null, "/grantr/v1/checks", {
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
              api.grantr.GET("grantr.list_members", "/grantr/v1/tenants/{tenant}/members", {
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
              api.grantr.GET("grantr.list_grants", "/grantr/v1/tenants/{tenant}/grants", {
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
              api.grantr.GET(
                "grantr.list_restrictions",
                "/grantr/v1/tenants/{tenant}/restrictions",
                {
                  ...named(tenant),
                  params: { path: { tenant }, query: { workspace: ws } },
                },
              ),
            ),
        }),
      /** The tenant's custom roles (`grantr:define_role`). */
      roles: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.roles(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("grantr.list_roles", "/grantr/v1/tenants/{tenant}/roles", {
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
          queryFn: () => body(api.grantr.GET(null, "/grantr/v1/catalog")),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /** The tenant's groups, by name, with their members (`grantr:manage_groups`). */
      groups: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.groups(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("grantr.list_groups", "/grantr/v1/tenants/{tenant}/groups", {
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
              api.grantr.GET("grantr.read_audit", "/grantr/v1/tenants/{tenant}/audit", {
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
      /**
       * The deployment's audit log, from its end back, a page at a time, for an operator, `user`
       * (`grantr:grant_operator`): who was made an operator, and who stopped being one.
       */
      deploymentAudit: (user: string) =>
        infiniteQueryOptions({
          queryKey: keys.grantr.deploymentAudit(user),
          initialPageParam: null as number | null,
          queryFn: ({ pageParam }) =>
            body(
              api.grantr.GET("grantr.read_audit", "/grantr/v1/audit", {
                params: { query: { last: AUDIT_PAGE, before_seq: pageParam } },
              }),
            ),
          getNextPageParam: (page) => (page.length < AUDIT_PAGE ? undefined : page[0]?.seq),
        }),
      /**
       * Each integration as it is set on the tenant, or with a workspace named, in that workspace and
       * on its tenant, in the registry's order, and whether it is on: for those who may switch
       * them there (`grantr:manage_integrations`, grantr ADR-0034).
       */
      integrations: (tenant: string, ws?: string) =>
        queryOptions({
          queryKey: keys.grantr.integrationStates(tenant, ws),
          queryFn: () =>
            body(
              ws === undefined
                ? api.grantr.GET(
                    "grantr.list_integrations",
                    "/grantr/v1/tenants/{tenant}/integrations",
                    {
                      ...named(tenant),
                      params: { path: { tenant } },
                    },
                  )
                : api.grantr.GET(
                    "grantr.list_integrations",
                    "/grantr/v1/tenants/{tenant}/workspaces/{workspace}/integrations",
                    {
                      ...named(tenant),
                      params: { path: { tenant, workspace: ws } },
                    },
                  ),
            ),
        }),
      /**
       * Each setting as it is narrowed on the tenant, or with a workspace named, in that
       * workspace and on its tenant: every layer, the ceiling and who set it, and the keys no
       * registry declares any more, for those who may narrow them there
       * (`grantr:manage_settings`, lattice ADR-0030).
       */
      settings: (tenant: string, ws?: string) =>
        queryOptions({
          queryKey: keys.grantr.settingStates(tenant, ws),
          queryFn: () =>
            body(
              ws === undefined
                ? api.grantr.GET("grantr.list_settings", "/grantr/v1/tenants/{tenant}/settings", {
                    ...named(tenant),
                    params: { path: { tenant } },
                  })
                : api.grantr.GET(
                    "grantr.list_settings",
                    "/grantr/v1/tenants/{tenant}/workspaces/{workspace}/settings",
                    {
                      ...named(tenant),
                      params: { path: { tenant, workspace: ws } },
                    },
                  ),
            ),
        }),
      /**
       * Whether each integration is on in a workspace, by key, for anyone who can open it. It is
       * read once and kept five minutes: after that, the window regaining focus or the network
       * coming back reads it again, as TanStack Query does, and a command refused as
       * `not_enabled` makes it stale at once (`stale.refusal`, portalr ADR-0045). A failed read
       * isn't tried again: each integration is its default until the next read.
       */
      enabledIntegrations: (tenant: string, ws: string) =>
        queryOptions({
          queryKey: keys.grantr.enabledIntegrations(tenant, ws),
          queryFn: () =>
            body(
              api.grantr.GET(
                null,
                "/grantr/v1/tenants/{tenant}/workspaces/{workspace}/enabled-integrations",
                { ...named(tenant), params: { path: { tenant, workspace: ws } } },
              ),
            ),
          staleTime: 5 * 60_000,
          retry: false,
        }),
      /** The tenant's keys, by public id and principal, never their secrets (`grantr:issue_key`). */
      keyring: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.keyring(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("grantr.list_keys", "/grantr/v1/tenants/{tenant}/keys", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
      /**
       * The approvals pending in the tenant that the caller may answer, oldest first, from every
       * workspace: those whose answerers they are among (grantr ADR-0040).
       */
      approvals: (tenant: string) =>
        queryOptions({
          queryKey: keys.grantr.approvalList(tenant),
          queryFn: () =>
            body(
              api.grantr.GET("grantr.list_approvals", "/grantr/v1/tenants/{tenant}/approvals", {
                ...named(tenant),
                params: { path: { tenant } },
              }),
            ),
        }),
      /**
       * One approval as it stands, whatever its state, for one who may answer it or the person
       * it was asked for; to anyone else, and in another tenant, it isn't there (404).
       */
      approval: (tenant: string, id: string) =>
        queryOptions({
          queryKey: keys.grantr.approval(tenant, id),
          queryFn: () =>
            body(
              api.grantr.GET(
                "grantr.read_approval",
                "/grantr/v1/tenants/{tenant}/approvals/{approval}",
                {
                  ...named(tenant),
                  params: { path: { tenant, approval: id } },
                },
              ),
            ),
        }),
    },
    portalr: {
      /**
       * The emails of people by their ids, as far as the server lets the reader see them (portalr
       * ADR-0038): at most `PEOPLE_MAX` ids to a request, and those the server names, by id. It
       * is asked in a tenant, or by an operator with none. It is kept five minutes, in memory,
       * is not tried again, and is not read again as the window regains focus.
       */
      people: (tenant: string | null, ids: readonly string[]) =>
        queryOptions({
          queryKey: keys.portalr.people(tenant, ids),
          queryFn: async () => {
            const emails: Record<string, string> = {};
            for (let from = 0; from < ids.length; from += PEOPLE_MAX) {
              const { people } = await body(
                api.portalr.GET(null, "/portalr/v1/people", {
                  ...(tenant === null ? {} : named(tenant)),
                  params: { query: { id: ids.slice(from, from + PEOPLE_MAX) } },
                }),
              );
              Object.assign(emails, people);
            }
            return emails;
          },
          staleTime: 5 * 60_000,
          gcTime: 5 * 60_000,
          retry: false,
          refetchOnWindowFocus: false,
        }),
      /** The tenant's spend against its budget, from its LiteLLM team. */
      spend: (tenant: string) =>
        queryOptions({
          queryKey: keys.portalr.spend(tenant),
          queryFn: () =>
            body(api.portalr.GET("portalr.read_spend", "/portalr/v1/spend", named(tenant))),
        }),
      /** The tenant's feedback and evaluation scores in a window, from Langfuse. */
      scores: (tenant: string, window: TimeSpan) =>
        queryOptions({
          queryKey: keys.portalr.scores(tenant, window),
          queryFn: () =>
            body(
              api.portalr.GET("portalr.read_scores", "/portalr/v1/scores", {
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
              api.portalr.GET("portalr.read_metrics", "/portalr/v1/metrics", {
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
              api.portalr.GET("portalr.read_feedback", "/portalr/v1/feedback", {
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
              api.portalr.GET("portalr.read_usage", "/portalr/v1/usage", {
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
       * The tenant's adoption over a window, from its product analytics: people active each day,
       * by integration, the funnel and weekly retention (portalr ADR-0071).
       */
      adoption: (tenant: string, window: TimeSpan) =>
        queryOptions({
          queryKey: keys.portalr.adoption(tenant, window),
          queryFn: () =>
            body(
              api.portalr.GET("portalr.read_adoption", "/portalr/v1/adoption", {
                ...named(tenant),
                params: { query: { start: window.start, end: window.end } },
              }),
            ),
          // Four reads of ClickHouse over the window: kept a while, and tried again once.
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
              api.portalr.GET("portalr.list_traces", "/portalr/v1/traces", {
                ...named(tenant),
                params: {
                  query: {
                    start: window.start,
                    end: window.end,
                    limit: TRACES_LIMIT,
                    ...(filter.session && { session: filter.session }),
                    ...(filter.run && { run: filter.run }),
                    ...(filter.analytics_session && {
                      analytics_session: filter.analytics_session,
                    }),
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
              api.portalr.GET("portalr.read_logs", "/portalr/v1/logs", {
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
              api.portalr.GET("portalr.read_log_line", "/portalr/v1/logs/{record_id}", {
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
              api.portalr.GET("portalr.read_trace", "/portalr/v1/traces/{trace_id}", {
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
              api.portalr.GET("portalr.deployment_links", "/portalr/v1/deployment/links", {
                params: { query: { trace_id: trace } },
              }),
            ),
          staleTime: Number.POSITIVE_INFINITY,
        }),
      /**
       * An operator's links into Langfuse and Grafana for the ids given. Each read is one that the
       * server records, so it is never kept: not fresh, not cached once nothing shows it, and not
       * read again on focus, on reconnecting, or by a retry.
       */
      toolLinks: (user: string, ids: ToolIds) =>
        queryOptions({
          queryKey: keys.portalr.toolLinks(user, ids),
          queryFn: () =>
            body(
              api.portalr.GET("portalr.deployment_links", "/portalr/v1/deployment/links", {
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
          refetchOnReconnect: false,
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
              return await body(
                api.portalr.GET(
                  "portalr.list_deployment_tenants",
                  "/portalr/v1/deployment/tenants",
                ),
              );
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

  /**
   * reflexr's rule events make its rules stale, its run events its runs, and an attempt's end
   * what the runs filed in a tracker too; ticks make its schedules stale.
   */
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
      case "reflexr:run_retrying":
      case "reflexr:run_succeeded":
      case "reflexr:run_dead_lettered":
        return [keys.reflexr.runs(tenant, ws), keys.relayr.filed(tenant, ws)];
      case "reflexr:run_started":
      case "reflexr:run_progressed":
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

  /**
   * A command artifactr refused as `not_enabled` makes the workspace's integrations stale: the
   * server says one is off that the page thought on, so it reads them again (portalr ADR-0045).
   */
  refusal(tenant: string, ws: string, result: Result) {
    return result.rejection?.type === "not_enabled"
      ? [keys.grantr.enabledIntegrations(tenant, ws)]
      : [];
  },
};
