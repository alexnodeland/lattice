/**
 * Uploading files as new native files (native files ADR-0017): chosen or dropped, several at once,
 * each sent in turn with how far it has gone, stoppable, and what came of it said in words. Each
 * file's kind is the one whose extension its name has, among those the workspace takes; one of no
 * kind, of several, of an app that is off, or too large never goes. The bytes go from the reader's
 * disk to artifactr's route as they are: the portal never reads them. Each file is sent with an id
 * chosen once, so one sent again after an answer that never came is never made twice.
 *
 * Shown only to those who may upload; what the workspace takes is read again every half minute,
 * as the kill switch reads its integrations, so an app switched off is soon off here too.
 */

import { newArtifactId, type UploadAnswer, uploadFile } from "@portalr/client";
import {
  FileChooser,
  fileSize,
  plainName,
  TextLink,
  type UploadItem,
  UploadList,
} from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type ReactNode, useEffect, useRef, useState } from "react";
import type { Context } from "./context";
import { NATIVE } from "./renderers";

type Kinds = readonly { readonly kind: string; readonly extensions: readonly string[] }[];

/** A file on the list, with what sending it needs. */
interface Queued extends UploadItem {
  readonly file: File;
  readonly kind: string;
  /** The id it is made with, chosen once, so that sending it again makes nothing twice. */
  readonly artifact: string;
  /** How many times it was sent again. */
  readonly tries: number;
}

/** How many times a file the app couldn't finish is offered to be sent again. */
const RETRIES = 2;

/** The app that reads a kind, as people call it, such as "WordCraft". */
export const appOf = (kind: string) => NATIVE.get(kind)?.app ?? kind;

/** The kinds whose extension a file's name has: none, one, or, ambiguously, several. */
export function kindsOf(name: string, kinds: Kinds): string[] {
  const extension = name.match(/\.[^.]+$/)?.[0]?.toLowerCase();
  return kinds
    .filter((kind) => kind.extensions.some((e) => e.toLowerCase() === extension))
    .map((kind) => kind.kind);
}

/**
 * Why an upload wasn't done, as the reader can act on it, and whether sending it again may do it:
 * never the app's own words, which a file can shape, nor the server's beyond its own.
 */
export function uploadRefused(
  answer: Exclude<UploadAnswer, { outcome: "done" }>,
  name: string,
  app: string,
  limit: number,
): { text: string; again: boolean } {
  const room = answer.quota?.startsWith("tenant") ? "Your organisation" : "This workspace";
  const what = answer.quota?.endsWith("files") ? "as many files" : "as much";
  switch (answer.status) {
    case 0:
      return {
        text: `${name} wasn't uploaded: the connection ended, or it was stopped, before the server answered. It may have arrived: trying again never makes it twice.`,
        again: true,
      };
    case 401:
      return {
        text: `${name} wasn't uploaded: you're signed out. Sign in, then try again.`,
        again: false,
      };
    case 403:
      return {
        text: `${name} wasn't uploaded: you can't upload files in this workspace.`,
        again: false,
      };
    case 408:
      return {
        text: `${name} wasn't uploaded: the upload was too slow and was stopped. Try again.`,
        again: true,
      };
    case 409:
      return answer.type === "not_enabled"
        ? { text: `${name} wasn't uploaded: ${app} is off in this workspace.`, again: false }
        : {
            text: `${name} wasn't uploaded: another file already has its id. Choose it again to upload it anew.`,
            again: false,
          };
    case 413:
      return answer.type === "over_quota"
        ? {
            text: `${name} wasn't uploaded: ${room} already holds ${what} as it may. Ask an admin for more room.`,
            again: false,
          }
        : { text: `${name} is larger than the ${fileSize(limit)} an upload takes.`, again: false };
    case 422:
      return {
        text: `${app} couldn't read ${name}: it may be damaged, or not the kind of file its name says.`,
        again: false,
      };
    case 429:
      return answer.type === "busy"
        ? {
            text: `${name} wasn't uploaded: the server is busy with other files just now. Try again in a few seconds.`,
            again: true,
          }
        : {
            text: `${name} wasn't uploaded: you've started many uploads in the last minute. Try again in a minute.`,
            again: true,
          };
    case 503:
      return {
        text: `${app} couldn't finish reading ${name}. Try again in a moment.`,
        again: true,
      };
    default:
      return { text: `${name} wasn't uploaded: the server refused it.`, again: false };
  }
}

export function Uploader({
  context,
  tenant,
  workspace,
  thread,
}: {
  context: Context;
  tenant: string;
  workspace: string;
  /** The thread the files are made in, if any. */
  thread?: string;
}) {
  const { data: offered } = useQuery(context.queries.files.uploads(tenant, workspace));
  const [items, setItems] = useState<readonly Queued[]>([]);
  const [announced, setAnnounced] = useState("");
  const going = useRef<string | null>(null);
  const stop = useRef<AbortController | null>(null);
  const update = (id: string, change: Partial<Queued>) =>
    setItems((now) => now.map((item) => (item.id === id ? { ...item, ...change } : item)));

  const send = async (item: Queued, limit: number) => {
    going.current = item.id;
    stop.current = new AbortController();
    update(item.id, { state: "sending", sent: 0, said: undefined });
    setAnnounced(`Uploading ${item.name}.`);
    const answer = await uploadFile({
      surface: context.config.surfaces.artifactr,
      session: context.signed.session(),
      tenant,
      workspace,
      kind: item.kind,
      name: item.name,
      artifact: item.artifact,
      ...(thread !== undefined && { thread }),
      file: item.file,
      onProgress: (sent) => update(item.id, { sent }),
      signal: stop.current.signal,
      unsigned: () => void context.signed.signOut(),
    });
    going.current = null;
    const app = appOf(item.kind);
    if (answer.outcome === "refused") {
      const { text, again } = uploadRefused(answer, item.name, app, limit);
      // The app crashing or timing out again and again is the file, not a blip: offered twice.
      const more = answer.status !== 503 || item.tries < RETRIES;
      update(item.id, { state: "failed", said: text, tone: "error", again: again && more });
      setAnnounced(text);
      return;
    }
    const text = {
      applied: `Uploaded ${item.name}.`,
      proposed: `${item.name} is a proposal, for an editor to accept:`,
      unchanged: `${item.name} was uploaded already: nothing new was made.`,
    }[answer.result.outcome];
    update(item.id, { state: "done", said: done(text, answer.result.outcome), tone: "info" });
    setAnnounced(text);
  };

  const done = (text: string, outcome: "applied" | "proposed" | "unchanged"): ReactNode =>
    outcome === "proposed" ? (
      <>
        {text}{" "}
        <TextLink
          render={<Link to="/t/$tenant/w/$workspace/proposals" params={{ tenant, workspace }} />}
        >
          the workspace's proposals
        </TextLink>
        .
      </>
    ) : (
      text
    );

  // Leaving the page stops the file going: the server may still have taken what was sent.
  useEffect(() => () => stop.current?.abort(), []);

  // One file at a time, in the order chosen: the next waits until the last has its answer.
  // `send` is each render's own, so this runs after every render; a file going stops it at once.
  useEffect(() => {
    if (offered === undefined || going.current !== null) {
      return;
    }
    const next = items.find((item) => item.state === "waiting");
    if (next !== undefined) {
      void send(next, offered.limit);
    }
  }, [items, offered, send]);

  if (offered === undefined || !offered.allowed) {
    return null;
  }
  const on = offered.kinds.filter((kind) => kind.enabled);
  const choose = (file: File) => {
    const name = plainName(file.name);
    const kinds = kindsOf(file.name, offered.kinds);
    const [kind] = kinds;
    // A kind's own limit, below the upload's where its app takes smaller files.
    const most = offered.kinds.find((k) => k.kind === kind)?.limit ?? offered.limit;
    const problem =
      kind === undefined
        ? `${name} isn't a kind of file this workspace takes.`
        : kinds.length > 1
          ? `${name} could be several kinds of file, so it can't be told which to make.`
          : !on.some((k) => k.kind === kind)
            ? `${appOf(kind)} is off in this workspace, so ${name} can't be uploaded.`
            : file.size > most
              ? `${name} is ${fileSize(file.size)}: the largest file of its kind an upload takes is ${fileSize(most)}.`
              : null;
    const item: Queued = {
      id: newArtifactId(),
      name,
      size: file.size,
      file,
      kind: kind ?? "",
      artifact: newArtifactId(),
      tries: 0,
      ...(problem === null
        ? { state: "waiting" }
        : { state: "failed", said: problem, tone: "error", again: false }),
    };
    if (problem !== null) {
      setAnnounced(problem);
    }
    setItems((now) => [...now, item]);
  };
  const extensions = on.flatMap((kind) => kind.extensions);
  // The kinds' extensions by the largest file each takes, the largest first: ".docx, .pdf up to
  // 26 MB each; .fcproj up to 2.1 MB each".
  const byLimit = new Map<number, string[]>();
  for (const kind of on) {
    byLimit.set(kind.limit, [...(byLimit.get(kind.limit) ?? []), ...kind.extensions]);
  }
  const sizes = [...byLimit]
    .sort(([a], [b]) => b - a)
    .map(([most, shown]) => `${shown.join(", ")}, up to ${fileSize(most)} each`)
    .join("; ");
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <FileChooser
        label={thread === undefined ? "Upload files" : "Add files to this thread"}
        hint={
          on.length === 0
            ? "No app for files is on in this workspace: an admin can switch one on in its integrations."
            : `${sizes}.`
        }
        accept={extensions.join(",")}
        multiple
        disabled={on.length === 0}
        onFile={choose}
      />
      <UploadList
        items={items}
        onStop={() => stop.current?.abort()}
        onRemove={(id) => setItems((now) => now.filter((item) => item.id !== id))}
        onRetry={(id) =>
          setItems((now) =>
            now.map((item) =>
              item.id === id
                ? { ...item, state: "waiting", said: undefined, tries: item.tries + 1 }
                : item,
            ),
          )
        }
      />
      <p role="status" className="sr-only">
        {announced}
      </p>
    </div>
  );
}
