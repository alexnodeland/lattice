import { keys, Refused } from "@portalr/client";
import { Button, TextField } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, notFound, useNavigate } from "@tanstack/react-router";
import { useActionState, useMemo, useState } from "react";
import { allowedIn } from "../../../../../../../allowed";
import { read, refusal } from "../../../../../../../rules";

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
  head: ({ params }) => ({ meta: [{ title: `${params.rule} · ${params.workspace} · portalr` }] }),
  // Another rule's page starts its editor afresh.
  remountDeps: ({ params }) => params.rule,
  loader: async ({ context, params }) => {
    const { tenant, workspace, rule } = params;
    await context.queryClient.ensureQueryData(
      allowedIn(context.queries, tenant, workspace, ACTIONS, resource(workspace, rule)),
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
  notFoundComponent: () => (
    <section aria-labelledby="rule">
      <h2 id="rule" className="font-semibold text-lg">
        Rule not found
      </h2>
      <p>There's no rule here by that name: it may have been archived.</p>
    </section>
  ),
  component: RulePage,
});

/** A rule as its editor starts: indented JSON. */
const shown = (rule: unknown) => `${JSON.stringify(rule, null, 2)}\n`;

function RulePage() {
  const { tenant, workspace, rule: name } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const navigate = useNavigate();
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspace, ACTIONS, resource(workspace, name)),
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
  const [unarchived, archive, archiving] = useActionState(async () => {
    const answer = await commands.reflexr.send(tenant, workspace, {
      type: "archive_rule",
      rule: name,
      expected_version: base,
    });
    if (answer.outcome === "refused") {
      return refusal("The rule wasn't archived", answer);
    }
    await navigate({ to: "/t/$tenant/w/$workspace/rules", params: { tenant, workspace } });
    return null;
  }, null);

  const stored = held.origin === "stored";
  return (
    <section aria-labelledby="rule" className="flex flex-col gap-4">
      <h2 id="rule" className="font-semibold font-mono text-lg">
        {name}
      </h2>
      <p>{held.rule.description || "No description."}</p>
      <p className="text-muted">
        {stored
          ? `Stored in this workspace, version ${held.version}.`
          : "In the application's code, the same in every workspace."}
      </p>
      {stored && allowed.has("reflexr:update_rule") ? (
        <form aria-label="Edit the rule" className="flex flex-col gap-2" action={save}>
          {current > base && (
            <p role="status" className="flex flex-wrap items-center gap-2">
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
            </p>
          )}
          <TextField
            label="Rule, as reflexr's JSON"
            value={text}
            onValueChange={setText}
            error={refused}
            render={<textarea rows={20} className="font-mono" spellCheck={false} />}
            required
          />
          <Button type="submit" disabled={saving} className="self-start">
            Save
          </Button>
        </form>
      ) : (
        <section aria-label="The rule, as reflexr's JSON">
          <pre className="overflow-x-auto font-mono text-sm">{shown(held.rule)}</pre>
        </section>
      )}
      {stored && allowed.has("reflexr:archive_rule") && (
        <form aria-label="Archive the rule" className="flex flex-col gap-1" action={archive}>
          <Button type="submit" variant="secondary" disabled={archiving} className="self-start">
            Archive
          </Button>
          {unarchived && <p role="alert">{unarchived}</p>}
        </form>
      )}
    </section>
  );
}
