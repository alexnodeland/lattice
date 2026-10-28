/**
 * What a proposal of a `rule` would do, under its card (portalr ADR-0017): a new rule as its
 * pipeline, and an edit as what it changes, stage by stage, as a revision's changes are said,
 * against the version it was made on. A proposal of another kind, or an edit whose version can't
 * be read or whose patch doesn't apply, adds nothing.
 */

import type { Artifactr } from "@portalr/client";
import { changes } from "@portalr/client/diff";
import { Disclosure, ProposedChanges, RulePipeline, rule } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { Context } from "./context";
import { applyPatch } from "./json-patch";

const isObject = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

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
  const after = useMemo(
    () =>
      isObject(before) && edit.patch.kind === "json_patch"
        ? applyPatch(before, edit.patch.ops as Readonly<Record<string, unknown>>[])
        : null,
    [before, edit.patch],
  );
  return (
    isObject(before) &&
    after !== null && (
      <ProposedChanges before={before} after={after} renderer={rule} compare={changes} />
    )
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
  if (change?.type === "create_artifact" && change.kind === "rule" && isObject(change.data.rule)) {
    // Once it is decided, the rule is the artifact's, or was turned down: folded, to look back on.
    const pipeline = <RulePipeline rule={change.data.rule} />;
    return proposal.status === "open" ? (
      pipeline
    ) : (
      <Disclosure summary="The rule it proposed">{pipeline}</Disclosure>
    );
  }
  if (change?.type === "edit_artifact" && kind === "rule") {
    return <RuleEdit edit={change} place={place} />;
  }
  return null;
}
