/**
 * What a proposal of a `rule` would do, under its card (portalr ADR-0017): a new rule as its
 * pipeline, and an edit as what it changes, stage by stage, as a revision's changes are said,
 * against the version it was made on, which it names. An edit whose version can't be read or whose
 * patch doesn't apply says so, with its changes as sent. A proposal of another kind adds nothing.
 */

import type { Artifactr } from "@portalr/client";
import { changes } from "@portalr/client/diff";
import { type Data, JsonView, ProposedChanges, RulePipeline, rule } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { Context } from "./context";
import { applyPatch } from "./json-patch";

/** A proposed rule artifact's rule, or null. */
const proposedRule = (change: { kind: string; data: Data }) =>
  change.kind === "rule" && typeof change.data.rule === "object" && change.data.rule !== null
    ? (change.data.rule as Data)
    : null;

type Edit = Extract<NonNullable<Artifactr.Proposal["change"]>, { type: "edit_artifact" }>;

function RuleEdit({
  edit,
  place: { context, tenant, workspace },
}: {
  edit: Edit;
  place: { context: Context; tenant: string; workspace: string };
}) {
  const read = useQuery(context.queries.artifactr.revisions(tenant, workspace, edit.artifact_id));
  const before = read.data?.find((revision) => revision.version === edit.base_version)?.data;
  const latest = read.data?.reduce((most, revision) => Math.max(most, revision.version), 0);
  const after = useMemo(
    () => (edit.patch.kind === "json_patch" ? applyPatch(before, edit.patch.ops) : null),
    [before, edit.patch],
  );
  if (read.isPending) {
    return null;
  }
  // A version that can't be read gives no patch applied either.
  const failed = after === null;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted text-sm">
        {failed ? "Couldn't work out what this changes in" : "Compared with"} version{" "}
        {edit.base_version}
        {failed
          ? ". Its changes, as sent:"
          : latest === edit.base_version
            ? ", the latest."
            : `; the latest is ${latest}.`}
      </p>
      {failed ? (
        <JsonView data={edit.patch} name="changes" />
      ) : (
        <ProposedChanges before={before as Data} after={after} renderer={rule} compare={changes} />
      )}
    </div>
  );
}

/**
 * A rule proposal's body: `kind` is the kind of the artifact an edit would change, as the
 * workspace's log has it.
 */
export function RuleProposal({
  proposal,
  kind,
  place,
}: {
  proposal: Artifactr.Proposal;
  kind: string | undefined;
  place: { context: Context; tenant: string; workspace: string };
}) {
  const { change } = proposal;
  // A new rule, while it is open: once decided, it is the artifact's, or was turned down.
  if (change?.type === "create_artifact" && proposal.status === "open") {
    const drafted = proposedRule(change);
    return drafted && <RulePipeline rule={drafted} />;
  }
  if (change?.type === "edit_artifact" && kind === "rule") {
    return <RuleEdit edit={change} place={place} />;
  }
  return null;
}
