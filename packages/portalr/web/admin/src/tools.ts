/**
 * Tools' address and what it makes (portalr ADR-0035): the trace, session, run and tenant an
 * operator asks for links for, which links each gives, and when a link may be shown.
 */

import type { PortalrApi, ToolIds } from "@portalr/client";
import { isId } from "./traces";

type Links = PortalrApi.components["schemas"]["Links"];

/** The address's ids, each optional: an id that isn't one portalr takes is none. */
export function shownOf(search: Record<string, unknown>): Required<ToolIds> {
  const id = (value: unknown) => {
    const read = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
    return isId(read) ? read : undefined;
  };
  const tenant = typeof search.tenant === "string" ? search.tenant : "";
  return {
    trace: id(search.trace),
    session: id(search.session),
    run: id(search.run),
    // A tenant's id is any text but empty and with no `~`, as grantr takes one.
    tenant: tenant.trim() !== "" && !tenant.includes("~") ? tenant : undefined,
  };
}

/** The tenants an operator may ask for, by name: none for someone who isn't an operator. */
export const tenantsOf = (every: { readonly tenants: readonly string[] } | null): string[] =>
  [...(every?.tenants ?? [])].sort((a, b) => a.localeCompare(b));

/** Whether any id was given: without one there is nothing to make links for. */
export const asked = (ids: ToolIds) => Object.values(ids).some((value) => value !== undefined);

/** One link an id may give: the tool, what it opens, and where in the answer it is. */
export interface Door {
  readonly kind: keyof ToolIds;
  readonly tool: "langfuse" | "grafana";
  readonly label: string;
  readonly field: keyof Links;
}

/** Every link, by the kind of id that makes it. */
export const DOORS: readonly Door[] = [
  { kind: "trace", tool: "langfuse", label: "The trace in Langfuse", field: "langfuse_trace" },
  {
    kind: "trace",
    tool: "grafana",
    label: "The trace in Grafana, from Tempo",
    field: "grafana_trace",
  },
  {
    kind: "session",
    tool: "langfuse",
    label: "The session in Langfuse",
    field: "langfuse_session",
  },
  {
    kind: "run",
    tool: "grafana",
    label: "The run's logs in Grafana, from Loki",
    field: "grafana_logs",
  },
  {
    kind: "tenant",
    tool: "langfuse",
    label: "The tenant's traces in Langfuse",
    field: "langfuse_tenant",
  },
  {
    kind: "tenant",
    tool: "grafana",
    label: "The tenant's logs in Grafana, from Loki",
    field: "grafana_tenant_logs",
  },
  {
    kind: "tenant",
    tool: "grafana",
    label: "The tenant's traces in Grafana, from Tempo",
    field: "grafana_tenant_traces",
  },
];

/**
 * A link as an `href`, only if it is an address a browser opens as a page: http or https. Anything
 * else, a `javascript:` or `data:` address, or text that is no address, is none, so a link is never
 * a way to run what a server, or a tool's setting, put in it.
 */
export function safeHref(link: string | null | undefined): string | null {
  if (!link) {
    return null;
  }
  try {
    const { protocol } = new URL(link);
    return protocol === "http:" || protocol === "https:" ? link : null;
  } catch {
    return null;
  }
}

/** What the notice beside the links says, always: these tools are outside portalr's gates. */
export const NOTICE =
  "Langfuse and Grafana aren't scoped to a tenant, and they show what people and models said, " +
  "across every tenant: they are outside the gates that Traces and Logs keep that behind. Opening " +
  "them is recorded: who you are, which kinds of id you asked for, and, for a tenant, which.";
