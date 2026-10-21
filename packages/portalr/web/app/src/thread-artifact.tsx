/**
 * An artifact in the thread it was made in (portalr ADR-0052, ADR-0055): its latest version, read
 * over REST and again as the workspace's log moves on, through its kind's renderer, with a link to
 * its own page and, but for an app, which has its own, a full view. A mini app runs there, as the
 * person viewing the thread, under the kill switch; a form is sent from there, as that person; and
 * a native file is read there a page at a time, and checked out, or edited, as on its page.
 */

import type { Artifactr } from "@portalr/client";
import {
  Alert,
  AppHostContext,
  ArtifactContent,
  FormHostContext,
  factsOf,
  IconButton,
  InlineArtifact,
  Reading,
} from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Download } from "lucide-react";
import { useAppHost } from "./app-host";
import type { Context } from "./context";
import { useFormHost } from "./form-host";
import { KillSwitch } from "./kill-switch";
import { useDownload } from "./native-file";
import { NativeInline } from "./native-inline";
import { NATIVE, RENDERERS } from "./renderers";
import { titleOf } from "./titles";

/** What people call an artifact of a kind: a native file by its type, any other by its kind. */
export function kindName(kind: string, data: Readonly<Record<string, unknown>>): string {
  if (NATIVE.has(kind)) {
    return factsOf(data).type;
  }
  const words = kind.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function ThreadArtifact({
  context,
  tenant,
  workspace,
  artifact,
  me,
}: {
  context: Context;
  tenant: string;
  workspace: string;
  artifact: Artifactr.Artifact;
  /** The reader's user id, as whom a form is sent and a file checked out. */
  me: string;
}) {
  const { queries } = context;
  const apps = useAppHost(context.config);
  const forms = useFormHost({ queries, tenant, workspace, me, renderers: RENDERERS });
  const read = useQuery(queries.artifactr.revisions(tenant, workspace, artifact.id));
  const latest = read.data?.reduce<NonNullable<typeof read.data>[number] | undefined>(
    (newest, revision) => (newest && newest.version > revision.version ? newest : revision),
    undefined,
  );
  // Untitled, it is named by its kind: a person's as well as the agent's is made in a thread.
  const name =
    (latest && titleOf(latest.kind, latest.data)) ?? kindName(artifact.kind, latest?.data ?? {});
  const open = (
    <Link
      to="/t/$tenant/w/$workspace/artifacts/$artifact"
      params={{ tenant, workspace, artifact: artifact.id }}
    />
  );
  const native = NATIVE.get(artifact.kind);
  // A native file's download is the entry's header's, beside its page and its full view.
  const place = { context, tenant, workspace, artifact: artifact.id };
  const downloads = useDownload(place, latest && factsOf(latest.data).name);
  const fetching = downloads.saving === "saving";
  return (
    <InlineArtifact
      name={name}
      open={open}
      {...(native &&
        latest && {
          actions: (
            <IconButton
              label={fetching ? "Downloading…" : "Download"}
              icon={Download}
              disabled={fetching}
              focusableWhenDisabled
              onClick={() => void downloads.download(latest.version)}
            />
          ),
        })}
      {...(artifact.kind !== "app" && latest && { kind: kindName(latest.kind, latest.data) })}
    >
      {/* A read again that fails keeps what was read, so a running app keeps running. */}
      {latest === undefined && read.isError ? (
        <Alert tone="error">
          This {artifact.kind} couldn't be read. Reload the page to try again.
        </Alert>
      ) : latest === undefined ? (
        <Reading>Loading the {artifact.kind}…</Reading>
      ) : native ? (
        <NativeInline
          place={place}
          native={native}
          me={me}
          downloads={downloads}
          unserved={<ArtifactContent kind={latest.kind} data={latest.data} renderers={RENDERERS} />}
        />
      ) : (
        <FormHostContext value={forms}>
          <AppHostContext value={apps}>
            {latest.kind === "app" && (
              <KillSwitch queries={queries} tenant={tenant} workspace={workspace} />
            )}
            <ArtifactContent
              kind={latest.kind}
              data={latest.data}
              // The version is the read's, which the app's state and a form's submission are
              // written on; archiving is the log's, which arrives before the read again, so an
              // archived app stops at once.
              shown={{ id: artifact.id, version: latest.version, archived: artifact.archived }}
              renderers={RENDERERS}
            />
          </AppHostContext>
        </FormHostContext>
      )}
    </InlineArtifact>
  );
}
