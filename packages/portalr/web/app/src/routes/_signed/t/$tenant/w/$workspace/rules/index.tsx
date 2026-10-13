import { allowedIn, keys, refusal, workspaceOf } from "@portalr/client";
import {
  Button,
  Card,
  PageHeader,
  Row,
  RowLink,
  Rows,
  SectionTitle,
  StatusBadge,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useActionState, useMemo, useState } from "react";
import { read, SKELETON } from "../../../../../../../rules";
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
        allowedIn(context.queries, params.tenant, workspaceOf(params.workspace), ACTIONS),
      ),
    ]),
  component: Rules,
});

/** A time the server gave, in the reader's own zone, or never. */
function When({ at }: { at: string | null }) {
  return at === null ? "never" : <time dateTime={at}>{new Date(at).toLocaleString()}</time>;
}

function Rules() {
  const { tenant, workspace } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspaceOf(workspace), ACTIONS),
    [queries, tenant, workspace],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: rules } = useSuspenseQuery(queries.reflexr.rules(tenant, workspace));
  const { data: schedules } = useSuspenseQuery(queries.reflexr.schedules(tenant, workspace));
  // The list is read again as the log says a rule changed (`WorkspaceStreams`).
  const automation = useAutomation();

  // The field is held here, not by the form, which a sent action resets.
  const [text, setText] = useState(SKELETON);
  const [refused, install, pending] = useActionState(async () => {
    const parsed = read(text);
    if ("refused" in parsed) {
      return parsed.refused;
    }
    const answer = await commands.reflexr.send(tenant, workspace, {
      type: "install_rule",
      rule: parsed.rule,
      provenance: {},
    });
    if (answer.outcome === "refused") {
      return refusal("The rule wasn't installed", answer);
    }
    await queryClient.invalidateQueries({ queryKey: keys.reflexr.rules(tenant, workspace) });
    setText(SKELETON);
    return null;
  }, null);

  return (
    <>
      <PageHeader
        title="Rules"
        meta={`What reacts to events in ${workspace}, and the schedules that tick into it`}
      />
      <Connection snapshot={automation} waiting="the latest changes to the rules" />
      <Rows label="Rules">
        {rules.map((rule) => (
          <Row key={rule.rule} aria-label={`Rule ${rule.rule}`}>
            <RowLink
              className="font-mono"
              render={
                <Link
                  to="/t/$tenant/w/$workspace/rules/$rule"
                  params={{ tenant, workspace, rule: rule.rule }}
                />
              }
            >
              {rule.rule}
            </RowLink>
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
          </Row>
        ))}
      </Rows>
      <section aria-labelledby="schedules" className="flex flex-col gap-3">
        <SectionTitle id="schedules">Schedules</SectionTitle>
        {schedules.length === 0 ? (
          <p>No schedules tick into this workspace.</p>
        ) : (
          <Rows label="Schedules">
            {schedules.map((schedule) => (
              <Row key={schedule.schedule} aria-label={`Schedule ${schedule.schedule}`}>
                <code className="font-mono">{schedule.schedule}</code>
                <span className="text-muted">
                  next <When at={schedule.next_tick} />
                </span>
                <span className="text-muted">
                  last <When at={schedule.last_tick} />
                </span>
              </Row>
            ))}
          </Rows>
        )}
      </section>
      {allowed.has("reflexr:install_rule") && (
        <Card
          render={<form aria-labelledby="install" action={install} />}
          className="flex flex-col gap-3"
        >
          <SectionTitle id="install">Install a rule</SectionTitle>
          <TextField
            label="Rule, as reflexr's JSON"
            value={text}
            onValueChange={setText}
            error={refused}
            render={<textarea rows={14} className="font-mono" spellCheck={false} />}
            required
          />
          <Button type="submit" disabled={pending} className="self-start">
            Install
          </Button>
        </Card>
      )}
    </>
  );
}
