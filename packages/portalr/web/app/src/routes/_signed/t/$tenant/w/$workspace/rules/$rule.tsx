import { allowedIn, keys, Refused, refusal } from "@portalr/client";
import {
  Alert,
  Button,
  ButtonLink,
  ConfirmDialog,
  CRUMB,
  Disclosure,
  NotFound as NotFoundPage,
  PageHeader,
  StatusBadge,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound, useNavigate } from "@tanstack/react-router";
import { Fragment, type ReactNode, useActionState, useMemo, useState } from "react";
import { read } from "../../../../../../../rules";

const ACTIONS = ["reflexr:update_rule", "reflexr:archive_rule"] as const;

/** The rule a page is about, as grantr names it: the server checks its commands on it. */
const resource = (workspace: string, rule: string) =>
  ({ kind: "rule", workspace, id: rule }) as const;

/**
 * One of the workspace's rules: a code rule, read only, or a stored rule's current version,
 * which, where grantr allows, is edited as JSON or archived. Each change names the version it
 * replaces, so one made over someone else's is refused, not lost.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/rules/$rule")({
  head: ({ params, match }) => ({
    meta: [
      {
        title: match.context.title(
          `${match.status === "notFound" ? "Rule not found" : params.rule} · ${params.workspace}`,
        ),
      },
    ],
  }),
  // Another rule's page starts its editor afresh.
  remountDeps: ({ params }) => params.rule,
  loader: async ({ context, params }) => {
    const { tenant, workspace, rule } = params;
    await context.queryClient.ensureQueryData(
      allowedIn(context.queries, tenant, resource(workspace, rule), ACTIONS),
    );
    try {
      await context.queryClient.ensureQueryData(
        context.queries.reflexr.rule(tenant, workspace, rule),
      );
    } catch (error) {
      if (error instanceof Refused && error.status === 404) {
        throw notFound();
      }
      throw error;
    }
  },
  notFoundComponent: NotFound,
  component: RulePage,
});

/** A value of a rule's, as one line of its JSON. */
const line = (value: unknown) => JSON.stringify(value);

/**
 * When a rule fires, in words where it is the common shape, the events it is on and how it
 * matches them ("portal:ticket.opened, each"); its JSON otherwise.
 */
function when(condition: unknown): string {
  const { filter, pattern } = (condition ?? {}) as {
    filter?: { kind?: string; types?: unknown[] };
    pattern?: { kind?: string };
  };
  const types = filter?.kind === "on" ? filter.types : undefined;
  if (!types?.every((type) => typeof type === "string")) {
    return line(condition);
  }
  return [types.join(" or "), pattern?.kind].filter(Boolean).join(", ");
}

/**
 * What a rule says, as a person reads it (portalr ADR-0085): when, then, over what, and how it
 * retries, ahead of its JSON. Each is one line; a value with no words of its own is its JSON.
 */
function Summary({ rule }: { rule: Record<string, unknown> }) {
  const then = rule.then as { action?: string; params?: Record<string, unknown> } | undefined;
  const scope = (rule.scope as { fields?: string[] } | undefined)?.fields ?? [];
  const retry = rule.retry as { max_attempts?: number } | undefined;
  const parts: [string, ReactNode][] = [
    [
      "When",
      <code key="when" className="break-all font-mono text-xs">
        {when(rule.when)}
      </code>,
    ],
    [
      "Then",
      <code key="then" className="font-mono text-xs">
        {then?.action}
        {then?.params && Object.keys(then.params).length > 0 && ` ${line(then.params)}`}
      </code>,
    ],
    ["For each", scope.length > 0 ? scope.join(", ") : "the whole workspace"],
    ["Retries", `up to ${retry?.max_attempts ?? 5} attempts`],
    ["Starts", rule.start === "beginning" ? "from the log's beginning" : "from now on"],
  ];
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 rounded-(--card-radius) border border-line bg-surface p-(--card-pad) text-sm">
      {parts.map(([term, said]) => (
        <Fragment key={term}>
          <dt className="text-muted">{term}</dt>
          <dd className="min-w-0 break-words">{said}</dd>
        </Fragment>
      ))}
      <dt className="text-muted">State</dt>
      <dd>
        <StatusBadge tone={rule.enabled === false ? "stopped" : "done"}>
          {rule.enabled === false ? "Disabled" : "Enabled"}
        </StatusBadge>
      </dd>
    </dl>
  );
}

/** A rule as its editor starts: indented JSON. */
const shown = (rule: unknown) => `${JSON.stringify(rule, null, 2)}\n`;

function RulePage() {
  const { tenant, workspace, rule: name } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const navigate = useNavigate();
  const checks = useMemo(
    () => allowedIn(queries, tenant, resource(workspace, name), ACTIONS),
    [queries, tenant, workspace, name],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  // Read again as the log says the rule changed (`WorkspaceStreams`).
  const { data: held } = useSuspenseQuery(queries.reflexr.rule(tenant, workspace, name));
  const current = held.version ?? 0;

  // The field is held here, not by the form, which a sent action resets; and the version its
  // text was opened at, or last saved or loaded as, which a change says it replaces.
  const [text, setText] = useState(() => shown(held.rule));
  const [base, setBase] = useState(current);
  const [refused, save, saving] = useActionState(async () => {
    const parsed = read(text);
    if ("refused" in parsed) {
      return parsed.refused;
    }
    if (parsed.rule.name !== name) {
      return `The rule's name is ${name}; install a new rule to rename it.`;
    }
    const answer = await commands.reflexr.send(tenant, workspace, {
      type: "update_rule",
      rule: parsed.rule,
      expected_version: base,
      provenance: {},
    });
    if (answer.outcome === "refused") {
      return refusal("The rule wasn't saved", answer);
    }
    const outcome = answer.result.outcome;
    if (outcome?.type === "rule_version") {
      setBase(outcome.version);
    }
    await queryClient.invalidateQueries({ queryKey: keys.reflexr.rule(tenant, workspace, name) });
    return null;
  }, null);
  const [unarchived, setUnarchived] = useState<string | null>(null);
  async function archive() {
    const answer = await commands.reflexr.send(tenant, workspace, {
      type: "archive_rule",
      rule: name,
      expected_version: base,
    });
    if (answer.outcome === "refused") {
      setUnarchived(refusal("The rule wasn't archived", answer));
      return;
    }
    await navigate({ to: "/t/$tenant/w/$workspace/rules", params: { tenant, workspace } });
  }

  const stored = held.origin === "stored";
  return (
    <section aria-labelledby="rule" className="mx-auto flex w-full max-w-190 flex-col gap-6">
      <PageHeader
        id="rule"
        title={name}
        breadcrumbs={[
          {
            label: "Rules",
            render: (
              <Link
                to="/t/$tenant/w/$workspace/rules"
                params={{ tenant, workspace }}
                activeOptions={CRUMB}
              />
            ),
          },
        ]}
        meta={
          stored
            ? `Stored in this workspace, version ${held.version}.`
            : "In the application's code, the same in every workspace."
        }
        actions={
          stored &&
          allowed.has("reflexr:archive_rule") && (
            <ConfirmDialog
              label="Archive"
              look="danger-soft"
              title={`Archive ${name}?`}
              confirm="Archive the rule"
              onConfirm={archive}
            >
              Version {held.version} stops reacting to events in {workspace}. Its runs stay in the
              log.
            </ConfirmDialog>
          )
        }
      />
      {unarchived && <Alert tone="error">{unarchived}</Alert>}
      <p>{held.rule.description || "No description."}</p>
      <Summary rule={held.rule as Record<string, unknown>} />
      {stored && allowed.has("reflexr:update_rule") ? (
        <form aria-label="Edit the rule" className="flex flex-col gap-2" action={save}>
          {current > base && (
            <Alert tone="info">
              <span className="flex flex-wrap items-center gap-2">
                Version {current} was saved since you opened this.
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setText(shown(held.rule));
                    setBase(current);
                  }}
                >
                  Load version {current}
                </Button>
              </span>
            </Alert>
          )}
          <TextField
            label="Rule, as reflexr's JSON"
            value={text}
            onValueChange={setText}
            error={refused}
            render={<textarea rows={20} wrap="off" className="font-mono" spellCheck={false} />}
            required
          />
          <Button type="submit" disabled={saving} className="self-start">
            Save
          </Button>
        </form>
      ) : (
        // Its JSON, folded until asked (portalr ADR-0085).
        <Disclosure summary="The rule, as reflexr's JSON">
          <pre className="whitespace-pre-wrap break-words rounded-(--card-radius) border border-line bg-surface p-4 font-mono text-xs">
            {shown(held.rule)}
          </pre>
        </Disclosure>
      )}
    </section>
  );
}

function NotFound() {
  const { tenant, workspace } = Route.useParams();
  return (
    <NotFoundPage
      title="Rule not found"
      action={
        <ButtonLink
          render={<Link to="/t/$tenant/w/$workspace/rules" params={{ tenant, workspace }} />}
        >
          All rules
        </ButtonLink>
      }
    >
      There's no rule here by that name: it may have been archived.
    </NotFoundPage>
  );
}
