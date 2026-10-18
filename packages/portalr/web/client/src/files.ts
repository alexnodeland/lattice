/**
 * Native files' bytes, as the UIs move them (lattice RFC-0003). Every route asks for the session
 * and the tenant, so nothing is linked to directly: a page is read and shown as a `data:` URL,
 * which the UIs' policy allows where it allows no `blob:`, and a version is read as a `Blob`, for
 * the app to save. A check-in sends the edited file, and says how far it has gone.
 */

import type { Answer } from "./commands";
import type { components as Files } from "./generated/files.openapi";
import { reasons } from "./reasons";
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

/** Where a check-in goes: the surface native files are mounted on, and whose check-out it is. */
interface CheckIn {
  /** artifactr's surface, beside which native files' routes are mounted, such as `/artifactr/v1`. */
  readonly surface: string;
  readonly session: Session;
  readonly tenant: string;
  readonly workspace: string;
  readonly checkout: string;
  readonly file: Blob;
  /** Called as the file's bytes go, with how many of them have. */
  readonly onProgress?: (sent: number, total: number) => void;
  /** Stops sending; the server may still have taken what was sent. */
  readonly signal?: AbortSignal;
  /** Called when it is refused because no one is signed in, as a command refused so is. */
  readonly unsigned?: () => void;
}

/**
 * Check a file in, sending its bytes as the body: through `XMLHttpRequest`, which says how far an
 * upload has gone, as `fetch` doesn't. Its answer is a command's: done, with what the check-in
 * made, or refused, with why and the rejection's type, such as `invalid_state`; refused with
 * status 0 when nothing answered, or it was stopped, when it may still have landed. Sent again,
 * the same file never makes anything twice: the server answers `unchanged` where it landed as a
 * version, and refuses it as checked in already where it landed as a proposal.
 */
export function checkIn(request: CheckIn): Promise<Answer<CheckedIn>> {
  const { surface, session, tenant, workspace, checkout, file, onProgress, signal, unsigned } =
    request;
  const url = `${surface.replace(/\/$/, "")}/workspaces/${encodeURIComponent(workspace)}/checkouts/${encodeURIComponent(checkout)}/file`;
  return new Promise((settle) => {
    const unanswered = (reason: string) =>
      settle({ outcome: "refused", status: 0, reasons: [reason] });
    const stopped = "The check-in was stopped: what was sent may still have been checked in.";
    if (signal?.aborted) {
      unanswered(stopped);
      return;
    }
    const xhr = new XMLHttpRequest();
    const stop = () => xhr.abort();
    signal?.addEventListener("abort", stop, { once: true });
    xhr.onloadend = () => signal?.removeEventListener("abort", stop);
    xhr.open("PUT", url);
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
        settle({ outcome: "done", result: body as CheckedIn });
        return;
      }
      if (xhr.status === 401) {
        unsigned?.();
      }
      const type = rejectionType(body);
      settle({
        outcome: "refused",
        status: xhr.status,
        reasons: reasons(xhr.status, body),
        ...(type !== undefined && { type }),
      });
    };
    xhr.onerror = () => unanswered("The connection ended before the server answered.");
    xhr.onabort = () => unanswered(stopped);
    xhr.send(file);
  });
}

/** A refusal's rejection type, as artifactr's router gives it in `detail.type`, if any. */
function rejectionType(body: unknown): string | undefined {
  const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : null;
  return typeof detail === "object" &&
    detail !== null &&
    "type" in detail &&
    typeof detail.type === "string"
    ? detail.type
    : undefined;
}

/** A body as JSON, or as it came if it isn't JSON. */
function parsed(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
