import { keys } from "@portalr/client";
import { Button, TextField } from "@portalr/ui";
import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useActionState, useEffect, useMemo, useState } from "react";
import { allowedIn } from "../../../../../../../allowed";
import { read, refusal } from "../../../../../../../rules";
import { useAutomation } from "../../../../../../../workspace";

const ACTIONS = ["reflexr:update_rule", "reflexr:archive_rule"] as const;

/**
 * One of the workspace's rules: a code rule, read only, or a stored rule's current version,
 * which, where grantr allows, is edited as JSON or archived. Each change names the version it
 * replaces, so one made over someone else's is refused, not lost.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/rules/$rule")({
  head: ({ params }) => ({ meta: [{ title: `${params.rule} · ${params.workspace} · portalr` }] }),
  loader: ({ context, params }) =>
    Promise.all([
      context.queryClient.ensureQueryData(
        context.queries.reflexr.rule(params.tenant, params.workspace, params.rule),
      ),
      context.queryClient.ensureQueryData(
        allowedIn(context.queries, params.tenant, params.workspace, ACTIONS),
      ),
    ]),
  component: RulePage,
});

/** A rule as its editor starts: indented JSON. */
const shown = (rule: unknown) => `${JSON.stringify(rule, null, 2)}\n`;

function RulePage() {
  const { tenant, workspace, rule: name } = Route.useParams();
  const { queries, commands } = Route.useRouteContext();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspace, ACTIONS),
    [queries, tenant, workspace],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: held } = useSuspenseQuery(queries.reflexr.rule(tenant, workspace, name));
  // The log's version of the rule: when an active one passes what was read, it's read again.
  const logged = useAutomation().state.rules[name];
  const newer = logged !== undefined && !logged.archived && logged.version > (held.version ?? 0);
  useEffect(() => {
    if (newer) {
      void queryClient.invalidateQueries({ queryKey: keys.reflexr.rule(tenant, workspace, name) });
    }
  }, [newer, queryClient, tenant, workspace, name]);

  // The field is held here, not by the form, which a sent action resets; and the version its
  // text was opened at, or last saved as, which a change says it replaces.
  const [text, setText] = useState(() => shown(held.rule));
  const [base, setBase] = useState(held.version ?? 0);
  const [refused, save, saving] = useActionState(async () => {
    const parsed = read(text);
    if ("refused" in parsed) {
      return parsed.refused;
    }
    const answer = await commands.reflexr.send(
      tenant,
      workspace,
      { type: "update_rule", rule: parsed.rule, expected_version: base, provenance: {} },
      `update-${crypto.randomUUID()}`,
    );
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
  const [archived, archive, archiving] = useActionState(async () => {
    const answer = await commands.reflexr.send(
      tenant,
      workspace,
      { type: "archive_rule", rule: name, expected_version: base },
      `archive-${crypto.randomUUID()}`,
    );
    if (answer.outcome === "refused") {
      return refusal("The rule wasn't archived", answer);
    }
    queryClient.removeQueries({ queryKey: keys.reflexr.rule(tenant, workspace, name) });
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
          <TextField
            label="Rule, as reflexr's JSON"
            name="rule"
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
        <pre className="overflow-x-auto font-mono text-sm">{shown(held.rule)}</pre>
      )}
      {stored && allowed.has("reflexr:archive_rule") && (
        <form className="flex flex-col gap-1" action={archive}>
          <Button type="submit" variant="secondary" disabled={archiving} className="self-start">
            Archive
          </Button>
          {archived && <p role="alert">{archived}</p>}
        </form>
      )}
    </section>
  );
}
