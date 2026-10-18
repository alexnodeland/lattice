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
  const tenant = typeof search.tenant === "string" ? search.tenant.trim() : "";
  return {
    trace: id(search.trace),
    session: id(search.session),
    run: id(search.run),
    // A tenant's id is any text but empty and with no `~`, as grantr takes one.
    tenant: tenant !== "" && !tenant.includes("~") ? tenant : undefined,
  };
}

/** What an address or a form gave that is not taken, as a tool's page says: which, and what. */
export interface Ignored {
  readonly label: string;
  readonly value: string;
}

const LABELS = {
  trace: "Trace id",
  session: "Session id",
  run: "Run id",
  tenant: "Tenant",
} as const;

/** The most of an ignored id the address keeps, so it can't be made to hold a page of text. */
const MOST_IGNORED = 80;

/**
 * The ids in a search that `shownOf` leaves out, so the page can say it did. The router rewrites
 * an address to what was taken, and would lose them, so they stay in the address, as `ignored`,
 * until the next ask: what a search already says was ignored is kept, if it is well formed.
 */
export function ignoredOf(search: Record<string, unknown>): Ignored[] {
  const taken = shownOf(search);
  const found = (Object.keys(LABELS) as (keyof typeof LABELS)[]).flatMap((kind) => {
    const given = search[kind];
    const text = typeof given === "string" || typeof given === "number" ? String(given).trim() : "";
    return text !== "" && taken[kind] === undefined
      ? [{ label: LABELS[kind], value: text.slice(0, MOST_IGNORED) }]
      : [];
  });
  if (found.length > 0 || !Array.isArray(search.ignored)) {
    return found;
  }
  const labels = new Set<string>(Object.values(LABELS));
  return search.ignored.flatMap((each: unknown) => {
    const one = each as Partial<Ignored> | null;
    return one &&
      typeof one.label === "string" &&
      labels.has(one.label) &&
      typeof one.value === "string"
      ? [{ label: one.label, value: one.value.slice(0, MOST_IGNORED) }]
      : [];
  });
}

/** The tools a link can be into, in the order their links are listed. */
export const TOOLS: readonly Door["tool"][] = ["langfuse", "grafana"];

/** A tool's name as people read it. */
export const TOOL_NAME: Record<Door["tool"], string> = { langfuse: "Langfuse", grafana: "Grafana" };

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

/** What the notice beside the links says, always: these tools are outside portalr's gates. */
export const NOTICE =
  "Langfuse and Grafana aren't scoped to a tenant, and they show what people and models said, " +
  "across every tenant: they are outside the gates that Traces and Logs keep that behind. Links " +
  "made here are recorded: who you are, which kinds of id you asked for and, for a tenant, which. " +
  "A visit to either tool that doesn't start here, or from a link already copied, is not.";
