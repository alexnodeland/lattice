/**
 * A native file edited here, in its app's own browser build, at talk level 1+ (`bridged`,
 * artifactr's files ADR-0010, portalr ADR-0055): the page frames lattice's shim on the editor's
 * origin, which frames the build there; once the shim says the build is ready, the checked-out
 * version is opened in it, and each file the build saves is checked in. The page hears only the
 * frame it made, from the editor's origin, and sends the file nowhere else.
 */

import { checkIn, type FilesApi } from "@portalr/client";
import { Alert, Button, ConfirmDialog, Dialog, fileSize, StatusBadge } from "@portalr/ui";
import { useBlocker } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { checkedIn, type Place, refused, type Said } from "./check-out";
import { editingDirty, stopEditing } from "./editing";

type Status = FilesApi.components["schemas"]["FileStatus"];

/** Where the shim is served on an editor's origin, beside the build. */
const SHIM = "/.lattice/shim.html";

/** How long the build has to say it is ready before the page says it didn't start. */
const STARTS_WITHIN = 60_000;

/**
 * The shim, on the editor's origin, told which portal origin frames it, this page's own, for a
 * shim that serves several (portalr ADR-0084); or null where the editor is at no web address.
 */
function shimAt(editor: string): string | null {
  try {
    return `${new URL(SHIM, new URL(editor).origin).href}?host=${encodeURIComponent(location.origin)}`;
  } catch {
    return null;
  }
}

/** The most messages a second the page hears from the editor; the rest are dropped. */
const MESSAGES_A_SECOND = 50;

/** How often the check-out's time left is looked at while the editor holds unsaved changes. */
const LOOK_EVERY = 60_000;

/** How little time left on a check-out has it extended, while there are unsaved changes. */
const EXTEND_WITHIN = 15 * 60_000;

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
  flipped = false,
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
  /** Whether it took the preview's box, which "Back to preview" turns back to. */
  flipped?: boolean;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [phase, setPhase] = useState<Phase>("starting");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const src = shimAt(editor);
  const shim = src === null ? null : new URL(src).origin;
  // Never the portal's own origin: a frame allowed its origin's scripts would run beside the
  // session, whoever named the editor.
  const origin = shim === location.origin ? null : shim;
  const { artifact } = place;

  // Unsaved changes keep the page from being left without a word, keep the check-out from
  // running out, and keep another file's editor from opening (`editing.ts`).
  useEffect(() => {
    editingDirty(artifact, dirty);
    if (!dirty) {
      return;
    }
    const leaving = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", leaving);
    // Extended only once it is about to run out; a refusal is said once, as the check-in's would be.
    let told = false;
    const extend = setInterval(async () => {
      const { place: at, checkout: held, status: file, app: name, onSaid: say } = latest.current;
      const until = file.lease?.expires_at;
      if (until === undefined || Date.parse(until) - Date.now() > EXTEND_WITHIN) {
        return;
      }
      const answer = await at.context.commands.files.extend(at.tenant, at.workspace, held);
      if (answer.outcome !== "done" && !told) {
        told = true;
        say({
          tone: "warn",
          text: `${refused("Your check-out wasn't extended", answer, name)} Save your work from ${name} soon, or download it there.`,
        });
      }
    }, LOOK_EVERY);
    return () => {
      window.removeEventListener("beforeunload", leaving);
      clearInterval(extend);
    };
  }, [artifact, dirty]);
  useEffect(() => () => stopEditing(artifact), [artifact]);
  // Leaving for another page of the app with unsaved changes is asked about, as closing is.
  const leaving = useBlocker({
    // Another page, not another view of this one: a search or a hash leaves the editor in place.
    shouldBlockFn: ({ current, next }) =>
      latest.current.dirtyNow && current.pathname !== next.pathname,
    enableBeforeUnload: false,
    withResolver: true,
  });
  // The latest of what a message is handled with, so the listener, and the time the build has to
  // start, are set once for the frame, whatever renders meanwhile.
  const now = {
    place,
    status,
    app,
    version,
    checkout,
    onSaid,
    onEnded,
    onAnswered,
    dirtyNow: dirty,
  };
  const latest = useRef(now);
  latest.current = now;

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
      const { place: at, status: file, version: base } = latest.current;
      const { context, tenant, workspace, artifact } = at;
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
    // One save checked in at a time: another while it is sent is said, and not sent.
    let sending = false;
    const save = async (name: string, bytes: ArrayBuffer) => {
      const { place: at, status: file, app, checkout: held } = latest.current;
      const { onSaid: say, onEnded: ended } = latest.current;
      const { context, tenant, workspace } = at;
      const wanted = extensionOf(file.name);
      if (sending) {
        say({
          tone: "warn",
          text: `Your last save is still being checked in: save again once it is.`,
        });
        return;
      }
      if (extensionOf(name) !== wanted) {
        say({
          tone: "warn",
          text: `${app} saved ${name}, which isn't checked in: only a ${wanted} file is. Save it as ${file.name} to check it in.`,
        });
        return;
      }
      if (bytes.byteLength > file.limit) {
        say({
          tone: "error",
          text: `${app} saved ${name} at ${fileSize(bytes.byteLength)}: the largest file a check-in takes is ${fileSize(file.limit)}. It wasn't checked in.`,
        });
        return;
      }
      sending = true;
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
      sending = false;
      setSaving(false);
      latest.current.onAnswered(answer.outcome === "done" ? null : answer.status);
      if (answer.outcome === "done") {
        const text = checkedIn(answer.result, file.name, false);
        say({ tone: answer.result.outcome === "proposed" ? "warn" : "info", text });
        setDirty(false);
        ended();
      } else {
        // The editor stays open with the work in it: it can be saved again, or downloaded there.
        say({ tone: "error", text: refused("It wasn't checked in", answer, app) });
      }
    };
    let second = 0;
    let heardThisSecond = 0;
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
      const now = Math.floor(Date.now() / 1000);
      heardThisSecond = now === second ? heardThisSecond + 1 : 1;
      second = now;
      if (heardThisSecond > MESSAGES_A_SECOND) {
        return;
      }
      const message = data as { type: unknown; dirty?: unknown; name?: unknown; bytes?: unknown };
      if (message.type === "lattice:ready" && phaseNow === "starting") {
        void open();
      } else if (message.type === "lattice:dirty" && typeof message.dirty === "boolean") {
        // Told at once, so another file's editor isn't let open in between.
        editingDirty(latest.current.place.artifact, message.dirty);
        setDirty(message.dirty);
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
  }, [origin]);

  if (origin === null) {
    return (
      <Alert tone="error">
        {app}'s editor isn't at a web address of its own, so it can't open here.
      </Alert>
    );
  }
  return (
    <div className={flipped ? "flex h-full flex-col gap-2" : "flex flex-col gap-2"}>
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
        {dirty ? (
          <ConfirmDialog
            label={flipped ? "Back to preview" : "Close without saving"}
            size="sm"
            className="ms-auto"
            title={flipped ? `Back to the preview without saving?` : `Close ${app} without saving?`}
            confirm={flipped ? "Discard and go back" : "Close without saving"}
            dismiss="Keep editing"
            // Not while a save is being checked in: it would race the save on the same check-out.
            disabled={saving}
            onConfirm={async () => onClose()}
          >
            Your changes to {status.name} in {app} haven't been saved, so they aren't checked in.
            {flipped
              ? ` Going back discards them: to keep them, save in ${app} first.`
              : " Closing loses them."}
          </ConfirmDialog>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            className="ms-auto"
            disabled={saving}
            onClick={onClose}
          >
            {flipped ? "Back to preview" : `Close ${app}`}
          </Button>
        )}
      </div>
      {phase === "failed" && (
        <Alert tone="warn">
          {app} didn't start here. Close it, then download the file, edit it in {app} yourself, and
          check it in below.
        </Alert>
      )}
      <Dialog
        open={leaving.status === "blocked"}
        onOpenChange={(open) => {
          if (!open && leaving.status === "blocked") {
            leaving.reset();
          }
        }}
        title={`Leave ${app} without saving?`}
        description={`Your changes to ${status.name} in ${app} haven't been saved, so they aren't checked in. Leaving loses them.`}
        close="Stay"
      >
        <Button variant="danger" className="self-start" onClick={() => leaving.proceed?.()}>
          Leave without saving
        </Button>
      </Dialog>
      <iframe
        ref={frame}
        src={src ?? undefined}
        title={`${app}, editing ${status.name}`}
        // Its own origin, which can reach none of the portal's; it saves through the shim.
        // Its pickers and links, and the clipboard, as the pilot builds use them.
        sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-forms allow-popups"
        allow="clipboard-read; clipboard-write"
        referrerPolicy="no-referrer"
        className={`block w-full rounded-md border border-edge bg-paper forced-colors:border-[CanvasText] ${flipped ? "min-h-0 flex-1" : "h-[min(80dvh,48rem)]"}`}
      />
    </div>
  );
}
