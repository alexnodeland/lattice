/**
 * An artifact in the thread it was made in (portalr ADR-0052): its latest version, read over REST
 * and again as the workspace's log moves on, through its kind's renderer, with a link to its own
 * page. A mini app runs there, as the person viewing the thread, under the kill switch.
 */

import type { Artifactr } from "@portalr/client";
import {
  Alert,
  AppHostContext,
  ArtifactContent,
  InlineArtifact,
  Reading,
  TextLink,
} from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useAppHost } from "./app-host";
import type { Context } from "./context";
import { KillSwitch } from "./kill-switch";
import { RENDERERS } from "./renderers";
import { titleOf } from "./titles";

export function ThreadArtifact({
  context,
  tenant,
  workspace,
  artifact,
}: {
  context: Pick<Context, "config" | "queries">;
  tenant: string;
  workspace: string;
  artifact: Artifactr.Artifact;
}) {
  const { queries } = context;
  const apps = useAppHost(context.config);
  const read = useQuery(queries.artifactr.revisions(tenant, workspace, artifact.id));
  const latest = read.data?.reduce((a, b) => (b.version > a.version ? b : a));
  const name = (latest && titleOf(latest.kind, latest.data)) ?? `The agent's ${artifact.kind}`;
  const open = (
    <TextLink
      render={
        <Link
          to="/t/$tenant/w/$workspace/artifacts/$artifact"
          params={{ tenant, workspace, artifact: artifact.id }}
        />
      }
    >
      Open its page
    </TextLink>
  );
  return (
    <InlineArtifact name={name} open={open}>
      {read.isError ? (
        <Alert tone="error">
          This {artifact.kind} couldn't be read. Reload the page to try again.
        </Alert>
      ) : latest === undefined ? (
        <Reading>Loading the {artifact.kind}…</Reading>
      ) : (
        <AppHostContext value={apps}>
          {latest.kind === "app" && (
            <KillSwitch queries={queries} tenant={tenant} workspace={workspace} />
          )}
          <ArtifactContent
            kind={latest.kind}
            data={latest.data}
            // The log's version and archiving are ahead of the read until it is read again.
            shown={{ id: artifact.id, version: latest.version, archived: artifact.archived }}
            renderers={RENDERERS}
          />
        </AppHostContext>
      )}
    </InlineArtifact>
  );
}
