/**
 * What lets a page's forms be sent (lattice RFC-0005): a submission created over the workspace's
 * stream as the person viewing it, keyed by the principal artifactr keys them by, and a form a
 * dashboard's panel names, read over REST as its own page reads it.
 */

import type { createQueries } from "@portalr/client";
import {
  Alert,
  ArtifactContent,
  type FormHost,
  principalOf,
  Reading,
  type Renderers,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { CatchBoundary } from "@tanstack/react-router";
import { Suspense, useMemo } from "react";
import { useStream } from "./workspace";

type Queries = ReturnType<typeof createQueries>;

/** A form artifact, at its latest version, as a dashboard's panel shows it. */
function FormPanel({
  queries,
  tenant,
  workspace,
  id,
  renderers,
}: {
  queries: Queries;
  tenant: string;
  workspace: string;
  id: string;
  renderers: Renderers;
}) {
  const { data: revisions } = useSuspenseQuery(queries.artifactr.revisions(tenant, workspace, id));
  const latest = revisions.reduce<(typeof revisions)[number] | undefined>(
    (newest, revision) => (newest && newest.version > revision.version ? newest : revision),
    undefined,
  );
  if (latest?.kind !== "form") {
    return <Alert tone="warn">The form this panel names isn't one.</Alert>;
  }
  return (
    <ArtifactContent
      kind="form"
      data={latest.data}
      shown={{ id, version: latest.version }}
      renderers={renderers}
    />
  );
}

/**
 * The form host of a page in a workspace, for the person `me`: a submission is created over the
 * workspace's stream, and a dashboard's form is read where it is shown, its failure said there.
 */
export function useFormHost({
  queries,
  tenant,
  workspace,
  me,
  renderers,
}: {
  queries: Queries;
  tenant: string;
  workspace: string;
  me: string;
  renderers: Renderers;
}): FormHost {
  const stream = useStream();
  return useMemo(
    () => ({
      principal: principalOf(me),
      // Spread: an artifact's data is any JSON object, which an interface isn't to the compiler.
      submit: (id, submission) =>
        stream.send({
          type: "create_artifact",
          artifact_id: id,
          kind: "submission",
          data: { ...submission },
        }),
      form: (id) => (
        <CatchBoundary
          getResetKey={() => id}
          errorComponent={() => <Alert tone="error">This form couldn't be read.</Alert>}
        >
          <Suspense fallback={<Reading>Reading the form…</Reading>}>
            <FormPanel
              queries={queries}
              tenant={tenant}
              workspace={workspace}
              id={id}
              renderers={renderers}
            />
          </Suspense>
        </CatchBoundary>
      ),
    }),
    [queries, tenant, workspace, me, renderers, stream],
  );
}
