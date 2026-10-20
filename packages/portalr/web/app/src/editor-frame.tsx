/**
 * A native file edited here, in its app's own browser build, at talk level 1+ (`bridged`,
 * artifactr's files ADR-0010, portalr ADR-0055): the page frames lattice's shim on the editor's
 * origin, which frames the build there; once the shim says the build is ready, the checked-out
 * version is opened in it, and each file the build saves is checked in. The page hears only the
 * frame it made, from the editor's origin, and sends the file nowhere else.
 */

import { checkIn, type FilesApi } from "@portalr/client";
import { Alert, Button, StatusBadge } from "@portalr/ui";
import { useLayoutEffect, useRef, useState } from "react";
import { checkedIn, type Place, refused, type Said } from "./check-out";

type Status = FilesApi.components["schemas"]["FileStatus"];

/** Where the shim is served on an editor's origin, beside the build. */
const SHIM = "/.lattice/shim.html";

/** How long the build has to say it is ready before the page says it didn't start. */
const STARTS_WITHIN = 60_000;

/** The shim, on the editor's origin, or null where the editor is at no web address. */
function shimAt(editor: string): string | null {
  try {
    return new URL(SHIM, new URL(editor).origin).href;
  } catch {
    return null;
  }
}

/** An extension, such as ".xlsx", in lower case; or "" for a name without one. */
const extensionOf = (name: string) => name.match(/\.[^./]+$/)?.[0]?.toLowerCase() ?? "";

type Phase = "starting" | "opening" | "open" | "failed";

/**
 * The editor, framed, with the checked-out file open in it: whether it has unsaved changes, and
 * each save checked in as it comes. A save in another format, such as an export, isn't checked
 * in, and it says so. Once a save is checked in, the check-out has ended, and `onEnded` is told.
 */
export function EditorFrame({
  place,
  status,
  app,
  editor,
  checkout,
  version,
  onSaid,
  onEnded,
  onAnswered,
  onClose,
}: {
  place: Place;
  status: Status;
  app: string;
  /** The editor's address, on an origin of its own. */
  editor: string;
  checkout: string;
  /** The version checked out, which is opened in the editor. */
  version: number;
  onSaid: (said: Said | null) => void;
  onEnded: () => void;
  onAnswered: (refusal: number | null) => void;
  onClose: () => void;
}) {
  const { context, tenant, workspace, artifact } = place;
  const frame = useRef<HTMLIFrameElement>(null);
  const [phase, setPhase] = useState<Phase>("starting");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const src = shimAt(editor);
  const origin = src === null ? null : new URL(src).origin;
  // The latest of what a message is handled with, so the listener is added once.
  const latest = useRef({ status, version, checkout, onSaid, onEnded, onAnswered });
  latest.current = { status, version, checkout, onSaid, onEnded, onAnswered };

  // Heard from as the frame is put in the page, before it can load: a shim that is quick to say
  // it is ready isn't missed.
  useLayoutEffect(() => {
    if (origin === null) {
      return;
    }
    let phaseNow: Phase = "starting";
    const to = (next: Phase) => {
      phaseNow = next;
      setPhase(next);
    };
    const late = setTimeout(() => {
      if (phaseNow === "starting") {
        to("failed");
      }
    }, STARTS_WITHIN);
    const open = async () => {
      to("opening");
      const { status: file, version: base } = latest.current;
      try {
        const blob = await context.queryClient.fetchQuery(
          context.queries.files.content(tenant, workspace, artifact, base),
        );
        const bytes = await blob.arrayBuffer();
        frame.current?.contentWindow?.postMessage(
          { type: "lattice:open", name: file.name, bytes },
          origin,
          [bytes],
        );
        to("open");
      } catch {
        to("failed");
      }
    };
    const save = async (name: string, bytes: ArrayBuffer) => {
      const { status: file, checkout: held, onSaid: say, onEnded: ended } = latest.current;
      const wanted = extensionOf(file.name);
      if (extensionOf(name) !== wanted) {
        say({
          tone: "warn",
          text: `${app} saved ${name}, which isn't checked in: only a ${wanted} file is. Save it as ${file.name} to check it in.`,
        });
        return;
      }
      setSaving(true);
      const answer = await checkIn({
        surface: context.config.surfaces.artifactr,
        session: context.signed.session(),
        tenant,
        workspace,
        checkout: held,
        file: new File([bytes], file.name),
        unsigned: () => void context.signed.signOut(),
      });
      setSaving(false);
      latest.current.onAnswered(answer.outcome === "done" ? null : answer.status);
      if (answer.outcome === "done") {
        const text = checkedIn(answer.result, file.name, false);
        say({ tone: answer.result.outcome === "proposed" ? "warn" : "info", text });
        ended();
      } else {
        say({ tone: "error", text: refused("It wasn't checked in", answer, app) });
      }
    };
    const heard = (event: MessageEvent) => {
      const data: unknown = event.data;
      if (
        event.origin !== origin ||
        event.source !== frame.current?.contentWindow ||
        typeof data !== "object" ||
        data === null ||
        !("type" in data)
      ) {
        return;
      }
      const message = data as { type: unknown; dirty?: unknown; name?: unknown; bytes?: unknown };
      if (message.type === "lattice:ready" && phaseNow === "starting") {
        void open();
      } else if (message.type === "lattice:dirty") {
        setDirty(message.dirty === true);
      } else if (message.type === "lattice:failed") {
        to("failed");
      } else if (
        message.type === "lattice:save" &&
        typeof message.name === "string" &&
        message.bytes instanceof ArrayBuffer
      ) {
        void save(message.name, message.bytes);
      }
    };
    addEventListener("message", heard);
    return () => {
      clearTimeout(late);
      removeEventListener("message", heard);
    };
  }, [origin, app, context, tenant, workspace, artifact]);

  if (src === null) {
    return (
      <Alert tone="error">{app}'s editor isn't at a web address, so it can't open here.</Alert>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {phase === "failed" ? (
          <StatusBadge tone="stopped" live>
            {app} didn't open here
          </StatusBadge>
        ) : phase === "open" ? (
          saving ? (
            <StatusBadge tone="working" live>
              Checking in your save
            </StatusBadge>
          ) : dirty ? (
            <StatusBadge tone="waiting" live>
              Unsaved changes in {app}
            </StatusBadge>
          ) : (
            <StatusBadge tone="done" live>
              Open in {app}: saving there checks it in
            </StatusBadge>
          )
        ) : (
          <StatusBadge tone="working" live>
            Opening {status.name} in {app}
          </StatusBadge>
        )}
        <Button variant="secondary" size="sm" className="ms-auto" onClick={onClose}>
          {dirty ? "Close without saving" : `Close ${app}`}
        </Button>
      </div>
      {phase === "failed" && (
        <Alert tone="warn">
          {app} didn't start here. Close it, then download the file, edit it in {app} yourself, and
          check it in below.
        </Alert>
      )}
      <iframe
        ref={frame}
        src={src}
        title={`${app}, editing ${status.name}`}
        // Its own origin, which can reach none of the portal's; it saves through the shim.
        sandbox="allow-scripts allow-same-origin allow-downloads allow-modals"
        referrerPolicy="no-referrer"
        className="block h-[min(80dvh,48rem)] w-full rounded-md border border-edge bg-paper forced-colors:border-[CanvasText]"
      />
    </div>
  );
}
