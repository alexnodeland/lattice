/**
 * Native files' bytes, as the UIs move them (lattice RFC-0003). Every route asks for the session
 * and the tenant, so nothing is linked to directly: a page is read and shown as a `data:` URL,
 * which the UIs' policy allows where it allows no `blob:`, and a version is read as a `Blob`, for
 * the app to save. A check-in sends the edited file, and an upload a new one, each saying how far
 * it has gone.
 */

import type { Answer, Refusal } from "./commands";
import type { components as Files } from "./generated/files.openapi";
import { refusalSaid } from "./reasons";
import { named } from "./rest";
import { type Session, sessionHeaders } from "./session";

/** A PNG's bytes as a `data:` URL, typed as a PNG whatever the response said. */
export function pngDataUrl(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  // In chunks, so a large page never passes more arguments than a call takes.
  for (let at = 0; at < view.length; at += 0x8000) {
    binary += String.fromCharCode(...view.subarray(at, at + 0x8000));
  }
  return `data:image/png;base64,${btoa(binary)}`;
}

/** What a check-in made: a revision, a proposal if the file had moved on, or nothing. */
export type CheckedIn = Files["schemas"]["CheckedIn"];

/** What an upload made: a native file, a proposal of one, or nothing, where it was there. */
export type Uploaded = Files["schemas"]["Uploaded"];

/** What may be uploaded in a workspace: whether at all, how large, and of which kinds. */
export type Uploads = Files["schemas"]["Uploads"];

/** Which quota an upload would pass: the workspace's or the tenant's, of bytes or of files. */
export type Quota = "workspace_bytes" | "workspace_files" | "tenant_bytes" | "tenant_files";

/** A file's send's answer, as a command's: a refusal past a quota also says which. */
type Sent<R> = Exclude<Answer<R>, Refusal> | (Refusal & { readonly quota?: Quota });

/** An upload's answer. */
export type UploadAnswer = Sent<Uploaded>;

/** What every send of a file shares: the surface it goes to, as whom, and how it goes. */
interface Sending {
  /** artifactr's surface, beside which native files' routes are mounted, such as `/artifactr/v1`. */
  readonly surface: string;
  readonly session: Session;
  readonly tenant: string;
  readonly workspace: string;
  readonly file: Blob;
  /** Called as the file's bytes go, with how many of them have. */
  readonly onProgress?: (sent: number, total: number) => void;
  /** Stops sending; the server may still have taken what was sent. */
  readonly signal?: AbortSignal;
  /** Called when it is refused because no one is signed in, as a command refused so is. */
  readonly unsigned?: () => void;
}

/** Where a check-in goes: whose check-out it is. */
interface CheckIn extends Sending {
  readonly checkout: string;
}

/** What an upload makes: a native file of `kind`, named, with an id the client chose. */
interface Upload extends Sending {
  /** Its artifact kind, such as `word_document`; the server tells the format by the bytes. */
  readonly kind: string;
  readonly name: string;
  /** The id it is made with, chosen once per file, so sending it again makes nothing twice. */
  readonly artifact: string;
  /** The thread it is made in, if any. */
  readonly thread?: string;
}

/**
 * Check a file in, sending its bytes as the body. Its answer is a command's: done, with what the
 * check-in made, or refused, with why and the rejection's type, such as `invalid_state`; refused
 * with status 0 when nothing answered, or it was stopped, when it may still have landed. Sent
 * again, the same file never makes anything twice: the server answers `unchanged` where it landed
 * as a version, and refuses it as checked in already where it landed as a proposal.
 */
export function checkIn(request: CheckIn): Promise<Answer<CheckedIn>> {
  const path = `/checkouts/${encodeURIComponent(request.checkout)}/file`;
  return send<CheckedIn>("PUT", path, request, "check-in", "checked in");
}

/**
 * Upload a file as a new native file, sending its bytes as the body: the portal never reads them.
 * Its answer is as a check-in's. Sent again with the same `artifact`, after an answer that never
 * came, it never makes the file twice: the server answers `unchanged` where it landed.
 */
export function uploadFile(request: Upload): Promise<UploadAnswer> {
  const query = new URLSearchParams({
    kind: request.kind,
    name: request.name,
    artifact_id: request.artifact,
    ...(request.thread !== undefined && { thread_id: request.thread }),
  });
  return send<Uploaded>("POST", `/files?${query}`, request, "upload", "uploaded");
}

/** A new artifact id for an upload, chosen once per file: `art_` and 16 random hex digits. */
export function newArtifactId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return `art_${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

/**
 * Send a file as a request's body to a workspace's path, through `XMLHttpRequest`, which says how
 * far an upload has gone, as `fetch` doesn't.
 */
function send<R>(
  method: "PUT" | "POST",
  path: string,
  request: Sending,
  what: string,
  done: string,
): Promise<Sent<R>> {
  const { surface, session, tenant, workspace, file, onProgress, signal, unsigned } = request;
  const url = `${surface.replace(/\/$/, "")}/workspaces/${encodeURIComponent(workspace)}${path}`;
  return new Promise((settle) => {
    const unanswered = (reason: string) =>
      settle({ outcome: "refused", status: 0, reasons: [reason] });
    const stopped = `The ${what} was stopped: what was sent may still have been ${done}.`;
    if (signal?.aborted) {
      unanswered(stopped);
      return;
    }
    const xhr = new XMLHttpRequest();
    const stop = () => xhr.abort();
    signal?.addEventListener("abort", stop, { once: true });
    xhr.onloadend = () => signal?.removeEventListener("abort", stop);
    xhr.open(method, url);
    for (const [name, value] of Object.entries({
      ...sessionHeaders(session),
      ...named(tenant).headers,
      "Content-Type": "application/octet-stream",
    })) {
      xhr.setRequestHeader(name, value);
    }
    xhr.upload.onprogress = (progress) => onProgress?.(progress.loaded, progress.total);
    xhr.onload = () => {
      const body = parsed(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        settle({ outcome: "done", result: body as R });
        return;
      }
      if (xhr.status === 401) {
        unsigned?.();
      }
      const type = detailOf(body, "type");
      const quota = detailOf(body, "quota") as Quota | undefined;
      const { status } = xhr;
      void refusalSaid(status, body, true).then((said) =>
        settle({
          outcome: "refused",
          status,
          reasons: [said],
          ...(type !== undefined && { type }),
          ...(quota !== undefined && { quota }),
        }),
      );
    };
    xhr.onerror = () => unanswered("The connection ended before the server answered.");
    xhr.onabort = () => unanswered(stopped);
    xhr.send(file);
  });
}

/** A string a refusal's `detail` holds, such as its rejection `type`, as artifactr's router gives it. */
function detailOf(body: unknown, field: "type" | "quota"): string | undefined {
  const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : null;
  if (typeof detail !== "object" || detail === null || !(field in detail)) {
    return undefined;
  }
  const value = (detail as Record<string, unknown>)[field];
  return typeof value === "string" ? value : undefined;
}

/** A body as JSON, or as it came if it isn't JSON. */
function parsed(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
