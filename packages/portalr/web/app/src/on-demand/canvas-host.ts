/**
 * What a diagram's canvas acts through (portalr ADR-0074): the person's edits, sent on the
 * workspace's stream as their own commands, so each revision is theirs; a diagram's head, read
 * again after a conflict; and its images, uploaded and read over the diagrams' routes as the
 * person. On an app's page, its app host's place and the workspace's stream give them; a page
 * without them, such as the CSP harness's, provides its own through `CanvasHostContext`.
 */

import { type Answer, streamUrl } from "@portalr/client";
import {
  type DiagramFile,
  editRefusalSaid,
  mayEditDiagram,
  readDiagram,
  readDiagramImage,
  uploadDiagramImage,
} from "@portalr/client/diagrams";
import type { AppHost } from "@portalr/ui";
import { createContext, useMemo } from "react";
import { useStream } from "../workspace";
import { type Heard, type Presence, watchPresence } from "./presence";

/** A JSON Patch operation, as the canvas sends one. */
type CanvasOp = { readonly op: string; readonly path: string; readonly value: unknown };

/** An edit the canvas sends: on the version it was made from, with a summary of it. */
export interface CanvasEdit {
  readonly baseVersion: number;
  readonly ops: readonly CanvasOp[];
  readonly summary: string;
}

/** What a canvas's edit came to. */
export type Committed =
  | { readonly outcome: "applied"; readonly version: number }
  | { readonly outcome: "proposed" }
  | { readonly outcome: "conflict" }
  | { readonly outcome: "refused"; readonly said: string };

/** What the canvas acts through, for a diagram by its id. */
export interface CanvasHost {
  commit(id: string, edit: CanvasEdit): Promise<Committed>;
  /** A diagram's head: its version and its data, or null where it can't be read. */
  head(id: string): Promise<{ readonly version: number; readonly data: unknown } | null>;
  upload(id: string, image: Blob): Promise<Answer<DiagramFile>>;
  read(id: string, sha256: string): Promise<Blob | null>;
  /** Whether the person may edit the diagram: the canvas offers Edit only where they may. */
  mayEdit(id: string): Promise<boolean>;
  /** The diagram's presence, over a connection of the canvas's own; null where there is none. */
  presence(id: string, heard: (now: Heard) => void): Presence | null;
}

/** A canvas host a page gives in place of its route's. */
export const CanvasHostContext = createContext<CanvasHost | null>(null);

/** What a command sent on the stream came to, as `Stream.send` settles it. */
type Settled = { readonly outcome: string; readonly result?: unknown };

/**
 * What a canvas's edit came to, from what its command settled as: a version conflict, to move
 * onto the head; a refusal, said in the kit's words, never the server's (portalr ADR-0070).
 */
export function committedOf(sent: Settled, baseVersion: number): Committed {
  if (sent.outcome === "closed") {
    return { outcome: "refused", said: "The connection to the workspace closed." };
  }
  if (sent.outcome === "refused") {
    const type = (sent.result as { rejection?: { type?: unknown } } | undefined)?.rejection?.type;
    if (type === "version_conflict") return { outcome: "conflict" };
    return { outcome: "refused", said: editRefusalSaid(sent.result) };
  }
  const done = (sent.result as { outcome?: { type?: string; version?: number } } | undefined)
    ?.outcome;
  if (done?.type === "proposed") return { outcome: "proposed" };
  return { outcome: "applied", version: done?.version ?? baseVersion + 1 };
}

/** The canvas host of a page in a workspace: the stream, the reads and the routes, as the person. */
export function useCanvasHost(place: NonNullable<AppHost["place"]>): CanvasHost {
  const stream = useStream();
  return useMemo(() => {
    const at = (diagram: string) => ({
      surface: place.surfaces.artifactr,
      grantr: place.surfaces.grantr,
      session: place.signed.session(),
      tenant: place.tenant,
      workspace: place.workspace,
      diagram,
    });
    return {
      async commit(id, edit) {
        const sent = await stream.send({
          type: "edit_artifact",
          artifact_id: id,
          base_version: edit.baseVersion,
          patch: { kind: "json_patch", ops: [...edit.ops] as never },
          summary: edit.summary,
        });
        return committedOf(sent, edit.baseVersion);
      },
      head: (id) => readDiagram(at(id)),
      upload: (id, image) => uploadDiagramImage(at(id), image),
      read: (id, sha256) => readDiagramImage(at(id), sha256),
      mayEdit: (id) => mayEditDiagram(at(id)),
      presence: (id, heard) =>
        watchPresence(
          {
            url: () =>
              streamUrl(
                new URL(place.surfaces.artifactr, location.origin).href,
                place.workspace,
                place.signed.streamSession(place.tenant),
              ),
          },
          id,
          heard,
        ),
    };
  }, [place, stream]);
}
