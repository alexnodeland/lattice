import type { ToolIds } from "@portalr/client";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Reading,
  SectionTitle,
  SelectField,
  TextField,
  TextLink,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type SearchSchemaInput } from "@tanstack/react-router";
import { type FormEvent, useId } from "react";
import {
  asked,
  DOORS,
  type Ignored,
  ignoredOf,
  NOTICE,
  safeHref,
  shownOf,
  TOOL_NAME,
  TOOLS,
  tenantsOf,
} from "../../../tools";
import { ID_PATTERN } from "../../../traces";

const HEADER = (
  <PageHeader title="Tools" meta="Langfuse and Grafana, for the deployment's operators" />
);

/**
 * Links into Langfuse and Grafana for a trace, a session, a run or a tenant, for the deployment's
 * operators. Those tools aren't scoped to a tenant, and what they show isn't behind the gates of
 * Traces and Logs, so the page says so beside the links, and each time links are made, portalr
 * records who asked and for which kinds of id (portalr ADR-0035). The ids are in the address.
 */
export const Route = createFileRoute("/_signed/deployment/tools")({
  head: () => ({ meta: [{ title: "Tools · portalr admin" }] }),
  validateSearch: (search: Record<string, unknown> & SearchSchemaInput) => ({
    ...shownOf(search),
    ignored: ignoredOf(search),
  }),
  component: ToolsPage,
});

/** The page, for the ids the address names: other ids are another page, with nothing carried over. */
function ToolsPage() {
  const { ignored, ...ids } = Route.useSearch();
  return <Body key={JSON.stringify({ ids, ignored })} ids={ids} ignored={ignored} />;
}

function Body({ ids, ignored }: { ids: Required<ToolIds>; ignored: Ignored[] }) {
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Notice />
      {ignored.map((each) => (
        <Alert key={each.label} tone="warn">
          “{each.value}” isn't {each.label === "Tenant" ? "a tenant id" : "an id"} portalr takes, so
          it was ignored ({each.label}).
        </Alert>
      ))}
      <Ask ids={ids} />
      {asked(ids) ? (
        <Links ids={ids} />
      ) : (
        <EmptyState title="Enter an id">
          Give a trace's, a session's or a run's id, or choose a tenant, for its links.
        </EmptyState>
      )}
    </div>
  );
}

/** The standing notice: always on the page, whatever it shows. */
function Notice() {
  const heading = useId();
  return (
    <Card
      render={<aside aria-labelledby={heading} />}
      className="flex max-w-prose flex-col gap-2 border-line"
    >
      <SectionTitle id={heading}>These tools are outside portalr's gates</SectionTitle>
      <p className="text-sm">{NOTICE}</p>
    </Card>
  );
}

/** The ids to ask for, and the tenant to choose; asking puts them in the address. */
function Ask({ ids }: { ids: Required<ToolIds> }) {
  const navigate = Route.useNavigate();
  const { queries, user } = Route.useRouteContext();
  // The layout read it before letting an operator in.
  const { data: every } = useSuspenseQuery(queries.portalr.tenants(user));
  const tenants = tenantsOf(every);
  const heading = useId();
  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget));
    void navigate({ search: shownOf(form) });
  }
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Links for</SectionTitle>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={ask}>
        <TextField
          label="Trace id"
          name="trace"
          defaultValue={ids.trace ?? ""}
          autoComplete="off"
          spellCheck={false}
          pattern={`\\s*${ID_PATTERN}\\s*|`}
        />
        <TextField
          label="Session id"
          name="session"
          defaultValue={ids.session ?? ""}
          autoComplete="off"
          spellCheck={false}
          pattern={`\\s*${ID_PATTERN}\\s*|`}
        />
        <TextField
          label="Run id"
          name="run"
          defaultValue={ids.run ?? ""}
          autoComplete="off"
          spellCheck={false}
          pattern={`\\s*${ID_PATTERN}\\s*|`}
        />
        <SelectField
          label="Tenant"
          name="tenant"
          defaultValue={ids.tenant ?? ""}
          options={[
            { value: "", label: "No tenant" },
            ...(ids.tenant && !tenants.includes(ids.tenant)
              ? [{ value: ids.tenant, label: ids.tenant }]
              : []),
            ...tenants.map((tenant) => ({ value: tenant, label: tenant })),
          ]}
        />
        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <Button type="submit">Get links</Button>
        </div>
      </form>
    </Card>
  );
}

/** The links for the ids given: made once, by the server, which records it. */
function Links({ ids }: { ids: Required<ToolIds> }) {
  const { queries, user, config } = Route.useRouteContext();
  const links = useQuery(queries.portalr.toolLinks(user, ids));
  const heading = useId();
  if (links.isPending) {
    return <Reading>Making the links…</Reading>;
  }
  if (links.isError) {
    return (
      <Alert tone="error">
        The links couldn't be made:{" "}
        {links.error instanceof Error ? links.error.message : "an error"}.
      </Alert>
    );
  }
  const readers = config.readers;
  const doors = DOORS.filter((door) => ids[door.kind] !== undefined);
  const made = doors.filter((door) => safeHref(links.data[door.field]) !== null);
  const missing = TOOLS.filter(
    (tool) => doors.some((door) => door.tool === tool) && readers[tool] === false,
  );
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Links</SectionTitle>
      {made.length > 0 && (
        <ul className="flex flex-col gap-2">
          {made.map((door) => (
            <li key={door.field}>
              <TextLink
                render={
                  <a
                    href={safeHref(links.data[door.field]) ?? undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
              >
                {door.label}
              </TextLink>
            </li>
          ))}
        </ul>
      )}
      {missing.map((tool) => (
        <p key={tool} className="text-muted text-sm">
          {TOOL_NAME[tool]} isn't configured here, so it has no links.
        </p>
      ))}
      {made.length === 0 && missing.length === 0 && (
        <p className="text-muted text-sm">No link can be made for what was asked.</p>
      )}
    </section>
  );
}
