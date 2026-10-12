import { keys } from "@portalr/client";
import { Button, StatusBadge, TextField, TextLink } from "@portalr/ui";
import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useActionState, useEffect, useMemo, useState } from "react";
import { allowedIn } from "../../../../../../../allowed";
import { read, refusal, SKELETON } from "../../../../../../../rules";
import { Connection, useAutomation } from "../../../../../../../workspace";

const ACTIONS = ["reflexr:install_rule"] as const;

/**
 * The workspace's rules, code rules first, each with how far it has read the log, and the
 * schedules that tick into it; and, where grantr allows, a stored rule installed from its JSON.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/rules/")({
  head: ({ params }) => ({ meta: [{ title: `Rules · ${params.workspace} · portalr` }] }),
  loader: ({ context, params }) =>
    Promise.all([
      context.queryClient.ensureQueryData(
        context.queries.reflexr.rules(params.tenant, params.workspace),
      ),
      context.queryClient.ensureQueryData(
        context.queries.reflexr.schedules(params.tenant, params.workspace),
      ),
      context.queryClient.ensureQueryData(
        allowedIn(context.queries, params.tenant, params.workspace, ACTIONS),
      ),
    ]),
  component: Rules,
});

/** A time the server gave, in the reader's own zone. */
const when = (at: string | null) => (at === null ? "never" : new Date(at).toLocaleString());

function Rules() {
  const { tenant, workspace } = Route.useParams();
  const { queries, commands } = Route.useRouteContext();
  const queryClient = useQueryClient();
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspace, ACTIONS),
    [queries, tenant, workspace],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: rules } = useSuspenseQuery(queries.reflexr.rules(tenant, workspace));
  const { data: schedules } = useSuspenseQuery(queries.reflexr.schedules(tenant, workspace));
  const automation = useAutomation();
  // Each stored rule's version as the log has it: when one changes, the list is read again.
  const versions = Object.values(automation.state.rules)
    .map((rule) => `${rule.name}@${rule.version}${rule.archived ? "-" : ""}`)
    .join(" ");
  useEffect(() => {
    if (versions !== "") {
      void queryClient.invalidateQueries({ queryKey: keys.reflexr.rules(tenant, workspace) });
    }
  }, [versions, queryClient, tenant, workspace]);

  // The field is held here, not by the form, which a sent action resets.
  const [text, setText] = useState(SKELETON);
  const [refused, install, pending] = useActionState(async () => {
    const parsed = read(text);
    if ("refused" in parsed) {
      return parsed.refused;
    }
    const answer = await commands.reflexr.send(
      tenant,
      workspace,
      { type: "install_rule", rule: parsed.rule, provenance: {} },
      `install-${crypto.randomUUID()}`,
    );
    if (answer.outcome === "refused") {
      return refusal("The rule wasn't installed", answer);
    }
    await queryClient.invalidateQueries({ queryKey: keys.reflexr.rules(tenant, workspace) });
    setText(SKELETON);
    return null;
  }, null);

  return (
    <section aria-labelledby="rules" className="flex flex-col gap-6">
      <h2 id="rules" className="font-semibold text-lg">
        Rules
      </h2>
      <Connection snapshot={automation} waiting="the workspace's rules" />
      <ul aria-label="Rules" className="flex flex-col gap-2">
        {rules.map((rule) => (
          <li key={rule.rule} aria-label={`Rule ${rule.rule}`} className="flex flex-wrap gap-2">
            <TextLink
              render={
                <Link
                  to="/t/$tenant/w/$workspace/rules/$rule"
                  params={{ tenant, workspace, rule: rule.rule }}
                />
              }
            >
              {rule.rule}
            </TextLink>
            <span className="text-muted">
              {rule.origin === "code" ? "in code" : `stored, version ${rule.version}`}
            </span>
            <StatusBadge tone={rule.enabled ? "done" : "stopped"}>
              {rule.enabled ? "Enabled" : "Disabled"}
            </StatusBadge>
            <span className="text-muted">
              {rule.lag === 0 ? "caught up" : `${rule.lag} behind`}
            </span>
            {rule.dead_letters > 0 && (
              <span className="text-muted">
                {rule.dead_letters === 1 ? "1 dead letter" : `${rule.dead_letters} dead letters`}
              </span>
            )}
          </li>
        ))}
      </ul>
      <section aria-labelledby="schedules" className="flex flex-col gap-2">
        <h3 id="schedules" className="font-semibold">
          Schedules
        </h3>
        {schedules.length === 0 ? (
          <p>No schedules tick into this workspace.</p>
        ) : (
          <ul aria-label="Schedules" className="flex flex-col gap-2">
            {schedules.map((schedule) => (
              <li
                key={schedule.schedule}
                aria-label={`Schedule ${schedule.schedule}`}
                className="flex flex-wrap gap-2"
              >
                <code className="font-mono">{schedule.schedule}</code>
                <span className="text-muted">next {when(schedule.next_tick)}</span>
                <span className="text-muted">last {when(schedule.last_tick)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {allowed.has("reflexr:install_rule") && (
        <form aria-labelledby="install" className="flex flex-col gap-2" action={install}>
          <h3 id="install" className="font-semibold">
            Install a rule
          </h3>
          <TextField
            label="Rule, as reflexr's JSON"
            name="rule"
            value={text}
            onValueChange={setText}
            error={refused}
            render={<textarea rows={14} className="font-mono" spellCheck={false} />}
            required
          />
          <Button type="submit" disabled={pending} className="self-start">
            Install
          </Button>
        </form>
      )}
    </section>
  );
}
