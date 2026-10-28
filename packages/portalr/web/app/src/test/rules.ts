/**
 * A workspace, notes, where the agent drafted a rule in a thread: its proposal accepted, which
 * made `rule_1`, a second version of it that fires twice a quarter hour, and an edit of that
 * proposed since, that throttles less and filters more.
 */

const FLAGS = "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations";
const at = (seq: number, actor: unknown, event: unknown) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-27T09:00:00Z",
  workspace_id: "notes",
  actor,
  event,
});
const alice = { kind: "user", id: "alice" };
const agent = { kind: "agent", id: "agent", run_id: "run_1" };

const on = { kind: "on", types: ["portal:ticket.opened", "portal:ticket.reopened"] };
const severe = { kind: "where", field: "severity", op: "ge", value: 7 };

/** The rule as drafted, and first accepted. */
const DRAFTED = {
  name: "ops.page_on_severe_tickets",
  description: "Page on-call when severe tickets pile up.",
  when: {
    filter: { kind: "all", of: [on, severe] },
    pattern: { kind: "count", at_least: 3, within: "PT10M" },
    throttle: { at_most: 1, per: "PT15M" },
  },
  scope: { fields: ["service"] },
  // Its action, under the key reflexr names it by, which an object literal can't name safely.
  ...(JSON.parse(
    '{"then": {"action": "ops:page", "params": {"to": "oncall", "urgency": "high"}}}',
  ) as Record<string, unknown>),
  timeout: "PT30S",
};

/** Its second version: twice in a quarter hour. */
const TWICE = { ...DRAFTED, when: { ...DRAFTED.when, throttle: { at_most: 2, per: "PT15M" } } };

const PRODUCTION = { kind: "where", field: "env", op: "eq", value: "prod" };

/** The edit's patch, as artifactr's `diff` writes one: the throttle shorter, a filter added. */
const PATCH = {
  kind: "json_patch",
  ops: [
    { op: "replace", path: "/rule/when/throttle/per", value: "PT5M" },
    { op: "add", path: "/rule/when/filter/of/2", value: PRODUCTION },
  ],
};

export const FIRED = "It would have fired 4 times since 2026-10-20.";

const LOG = [
  at(1, alice, { type: "thread_created", thread_id: "thr_r", title: "Page on severe tickets" }),
  at(2, alice, {
    type: "message_posted",
    thread_id: "thr_r",
    message_id: "m1",
    content: "Page on-call when three severe tickets open within ten minutes.",
  }),
  at(3, agent, { type: "run_started", run_id: "run_1", thread_id: "thr_r" }),
  at(4, agent, {
    type: "proposal_created",
    proposal_id: "prop_1",
    thread_id: "thr_r",
    run_id: "run_1",
    rationale: `Pages on-call for a burst of severe tickets.\n\n${FIRED}`,
    change: {
      type: "create_artifact",
      artifact_id: "rule_1",
      kind: "rule",
      data: { rule: DRAFTED },
      thread_id: "thr_r",
    },
  }),
  at(5, alice, {
    type: "proposal_resolved",
    proposal_id: "prop_1",
    thread_id: "thr_r",
    decision: "accept",
  }),
  at(6, alice, {
    type: "artifact_created",
    artifact_id: "rule_1",
    kind: "rule",
    version: 2,
    thread_id: "thr_r",
  }),
  at(7, agent, {
    type: "proposal_created",
    proposal_id: "prop_2",
    thread_id: "thr_r",
    run_id: "run_1",
    rationale:
      "Production only, and every five minutes.\n\nIt would have fired 2 times since 2026-10-20.",
    change: {
      type: "edit_artifact",
      artifact_id: "rule_1",
      base_version: 2,
      summary: "Edit the rule",
      patch: PATCH,
      thread_id: "thr_r",
    },
  }),
  at(8, agent, { type: "run_ended", run_id: "run_1", thread_id: "thr_r", status: "completed" }),
  // relayr's rule-drift: the rule changed in reflexr directly, proposed back to its artifact by
  // the system, from no thread.
  at(
    9,
    { kind: "system", id: "relayr:rule-drift" },
    {
      type: "proposal_created",
      proposal_id: "prop_drift",
      rationale: "The rule was changed in reflexr directly.",
      change: {
        type: "edit_artifact",
        artifact_id: "rule_1",
        base_version: 2,
        summary: "Bring the rule in line with reflexr",
        patch: {
          kind: "json_patch",
          ops: [{ op: "replace", path: "/rule/scope/fields/0", value: "team" }],
        },
      },
    },
  ), // An edit whose patch doesn't apply: an array's `length` isn't an index.
  at(
    10,
    { kind: "system", id: "relayr:rule-drift" },
    {
      type: "proposal_created",
      proposal_id: "prop_bad",
      rationale: null,
      change: {
        type: "edit_artifact",
        artifact_id: "rule_1",
        base_version: 1,
        summary: "A patch that can't apply",
        patch: { kind: "json_patch", ops: [{ op: "remove", path: "/rule/scope/fields/length" }] },
      },
    },
  ),
];

export const serve = async (request: Request, path: string) => {
  if (path === "/grantr/v1/checks")
    return Response.json(((await request.json()) as unknown[]).map(() => true));
  if (path === FLAGS) return Response.json({});
  if (path === "/artifactr/v1/workspaces/notes/artifacts/rule_1/revisions")
    return Response.json([
      {
        artifact_id: "rule_1",
        version: 1,
        kind: "rule",
        data: { rule: DRAFTED },
        archived: false,
        actor: { kind: "user", id: "alice" },
      },
      {
        artifact_id: "rule_1",
        version: 2,
        kind: "rule",
        data: { rule: TWICE },
        archived: false,
        actor: { kind: "user", id: "alice" },
      },
    ]);
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

export const WORLD = { artifactrLog: LOG };
