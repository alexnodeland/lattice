/**
 * An artifact in the thread it was made in (portalr ADR-0052, ADR-0055): its latest version, read
 * over REST and again as the workspace's log moves on, through its kind's renderer, with a link to
 * its own page and, but for an app, which has its own, a full view. A mini app runs there, as the
 * person viewing the thread, under the kill switch; a form is sent from there, as that person; and
 * a native file is read there a page at a time, and checked out, or edited, as on its page. An
 * app runs in its newest card in the thread alone; one before it says which version it was.
 */

import type { Artifactr } from "@portalr/client";
import {
  Alert,
  AppHostContext,
  ArtifactContent,
  FormHostContext,
  factsOf,
  InlineArtifact,
  Reading,
} from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useAppHost } from "./app-host";
import type { Context } from "./context";
import { NativeInline } from "./files";
import { useFormHost } from "./form-host";
import { KillSwitch } from "./kill-switch";
import { NATIVE } from "./native";
import { RENDERERS } from "./renderers";
import { titleOf } from "./titles";

/** What people call an artifact of a kind: a native file by its type, any other by its kind. */
export function kindName(kind: string, data: Readonly<Record<string, unknown>>): string {
  return NATIVE.has(kind) && factsOf(data).type !== "File" ? factsOf(data).type : kindWords(kind);
}

/** Words written as capitals in a kind's name. */
const CAPITALS: Readonly<Record<string, string>> = { pdf: "PDF", cad: "CAD", svg: "SVG" };

/** A kind as words, without its data: `pdf_document` as "PDF document". */
export function kindWords(kind: string): string {
  const words = kind.split("_").map((word) => CAPITALS[word] ?? word);
  const first = words[0] ?? "";
  return [first.charAt(0).toUpperCase() + first.slice(1), ...words.slice(1)].join(" ");
}

export function ThreadArtifact({
  context,
  tenant,
  workspace,
  artifact,
  me,
  superseded,
}: {
  context: Context;
  tenant: string;
  workspace: string;
  artifact: Artifactr.Artifact;
  /** The reader's user id, as whom a form is sent and a file checked out. */
  me: string;
  /** For an app shown again further down: the version this card was, shown without running. */
  superseded?: number;
}) {
  const { queries } = context;
  const apps = useAppHost(context, tenant, workspace);
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
  // Where a native file puts its download, in the header beside its page and its full view,
  // once it is read and served (portalr ADR-0061).
  const [actions, setActions] = useState<HTMLElement | null>(null);
  return (
    <InlineArtifact
      name={name}
      open={open}
      {...(native && { actions: <span ref={setActions} className="contents" /> })}
      {...(artifact.kind !== "app" && latest && { kind: kindName(latest.kind, latest.data) })}
    >
      {/* A read again that fails keeps what was read, so a running app keeps running. */}
      {latest === undefined && read.isError ? (
        <Alert tone="error">
          This {artifact.kind} couldn't be read. Reload the page to try again.
        </Alert>
      ) : superseded !== undefined ? (
        <div className="flex flex-col gap-1">
          <span className="font-semibold text-sm">{name}</span>
          <p className="text-muted text-xs">
            Made by the agent. Version {superseded}. A newer version runs below.
          </p>
        </div>
      ) : latest === undefined ? (
        <Reading>Loading the {artifact.kind}…</Reading>
      ) : native ? (
        <NativeInline
          place={{ context, tenant, workspace, artifact: artifact.id }}
          native={native}
          me={me}
          header={actions}
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
