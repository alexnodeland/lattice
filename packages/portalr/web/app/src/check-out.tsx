/**
 * Checking a native file out and in (lattice RFC-0003, portalr ADR-0049). At the app's talk level
 * 1, save only, checking out holds the file, downloads its head, and opens its app's hosted editor
 * in a new tab, on an origin of its own; the person edits there and saves to their disk; checking
 * in uploads that file here, with how far it has gone, and says what it made. At level 1+
 * (`bridged`), the editor opens here instead, framed, with the file in it, and each save is
 * checked in as it is made (portalr ADR-0055); the download and the upload stay beneath it.
 */

import {
  type Answer,
  type CheckedIn,
  checkIn,
  type FilesApi,
  keys,
  type Refusal,
} from "@portalr/client";
import { Button, FileChooser, fileSize, Moment, Progress, TextLink } from "@portalr/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type ReactNode, use, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Context } from "./context";
import { startEditing, stopEditing, useEditing } from "./editing";
import { EditorFrame } from "./editor-frame";
import { ViewSlotsContext } from "./view-slots";

type Status = FilesApi.components["schemas"]["FileStatus"];

/** Where a check-out was sent from: the route's context, and the file. */
export interface Place {
  readonly context: Context;
  readonly tenant: string;
  readonly workspace: string;
  readonly artifact: string;
}

/** What came of the last thing the reader did here, as the section says it. */
export interface Said {
  readonly tone: "info" | "warn" | "error";
  readonly text: ReactNode;
  /** Said where the focus has gone elsewhere, as a flip moves it: announced, not focused. */
  readonly quiet?: boolean;
}

/**
 * The app's hosted editor, where it may be opened from here: on an origin of its own, never the
 * portal's, which would put the third party's build beside the session.
 */
export function editorAt(editors: Readonly<Record<string, string>>, key: string): string | null {
  const url = editors[key];
  if (url === undefined) {
    return null;
  }
  return new URL(url, location.href).origin === location.origin ? null : url;
}

/** A reason as a sentence: with its full stop, once. */
const sentence = (text: string) => (/[.!?]$/.test(text) ? text : `${text}.`);

/**
 * Why something wasn't done, as the reader can act on it, from the refusal's status and reasons.
 * A 422 is the app refusing the file, or the file not being one its kind holds.
 */
export function refused(undone: string, refusal: Refusal, app: string): string {
  const why = sentence(refusal.reasons.join("; "));
  switch (refusal.status) {
    case 0:
      return `${undone}: ${why} Try again.`;
    case 422:
      return `${undone}: ${app} couldn't read it. Check it's the file you saved from ${app}.`;
    case 503:
      return `${undone}: ${app} couldn't finish reading it. Try again in a moment.`;
    default:
      return `${undone}: ${why}`;
  }
}

/** What a check-in made, in words: one sent again after a lost answer that finds it in says so. */
export function checkedIn(answer: CheckedIn, name: string, again: boolean): string {
  switch (answer.outcome) {
    case "applied":
      return `Checked in ${name} as version ${answer.version}.`;
    case "proposed":
      return `${name} changed after you checked it out, so your check-in is a proposal, to review beside the version it would replace:`;
    case "unchanged":
      return again
        ? `${name} was checked in already: nothing new was made.`
        : `Nothing in ${name} changed, so no version was made. Your check-out has ended.`;
    default:
      return answer.outcome satisfies never;
  }
}

/**
 * The reader's own check-out of a file, kept in this tab's storage from when they check it out
 * until it ends, so that once its lease lapses, and the status no longer names it, it can still be
 * checked in. Storage may be refused, as in a private window: then a reload forgets it.
 */
function useOwnCheckout({ tenant, workspace, artifact }: Place) {
  const key = `portalr:checkout:${tenant}/${workspace}/${artifact}`;
  const [own, setOwn] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  });
  const keep = (id: string | null) => {
    setOwn(id);
    try {
      if (id === null) {
        sessionStorage.removeItem(key);
      } else {
        sessionStorage.setItem(key, id);
      }
    } catch {
      // Not kept: this tab still holds it until a reload.
    }
  };
  return [own, keep] as const;
}

/**
 * The reader's controls for a file: check it out while no one has it; while it is theirs, open
 * the editor, download it again and extend the check-out; and check the edited file in, while it
 * is theirs, and after its lease ran out, when a check-in that finds the file moved on is a
 * proposal.
 */
export function CheckOut({
  place,
  status,
  app,
  editor,
  onSaid,
  onDownload,
}: {
  place: Place;
  status: Status;
  /** The app's name, such as "WordCraft". */
  app: string;
  /** The hosted editor's address, or null where none is hosted, or none may be opened. */
  editor: string | null;
  onSaid: (said: Said | null) => void;
  /** Download a version of the file, as the section does. */
  onDownload: (version: number) => Promise<void>;
}) {
  const { context, tenant, workspace, artifact } = place;
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [own, keep] = useOwnCheckout(place);
  // Its build hands the file over and back where its editor is hosted: it is edited here.
  const here = editor !== null && status.talk === "bridged";
  // One file is edited in place on a page at a time; the version checked out is what it opens,
  // which, once the page is loaded again, is the head the lease still holds.
  const editing = useEditing()?.artifact === artifact;
  const [base, setBase] = useState<number | null>(null);
  const setEditing = (on: boolean) => {
    if (!on) {
      stopEditing(artifact);
      return true;
    }
    const busy = startEditing(artifact, status.name);
    if (busy !== null) {
      onSaid({
        tone: "warn",
        text: `${busy.name} is open in its editor with unsaved changes: save or close it first. One file is edited here at a time.`,
      });
    }
    return busy === null;
  };
  // In a thread, the editor takes the preview's box, and the switch to it sits above it.
  const slots = here ? use(ViewSlotsContext) : null;
  const flips = slots?.viewport != null && slots.toggle != null;
  /**
   * Back to the preview, the check-out let go: the version checked out is checked in again as it
   * was, which changes nothing and ends the check-out, so a file isn't held by a closed editor.
   */
  const release = async (held: string) => {
    if (pending) {
      return;
    }
    // Held, with the editor in place, until the check-out is let go: the switch to edit waits.
    setPending(true);
    // The head, not the version opened: checked in as it is, it is unchanged even where the file
    // moved on after the lease lapsed, so it never proposes the version opened over a newer one.
    const head = status.version;
    let ended = false;
    try {
      const blob = await queryClient.fetchQuery(
        context.queries.files.content(tenant, workspace, artifact, head),
      );
      const answer = await checkIn({
        surface: context.config.surfaces.artifactr,
        session: context.signed.session(),
        tenant,
        workspace,
        checkout: held,
        file: new File([blob], status.name),
        unsigned: () => void context.signed.signOut(),
      });
      reread(answer.outcome === "done" ? null : answer.status);
      // Checked in already, by a save that answered late or another tab: it has ended too.
      ended =
        answer.outcome === "done" || (answer.status === 409 && answer.type === "invalid_state");
    } catch {
      // Said below: the check-out stays, until it is checked in or runs out.
    }
    setPending(false);
    setEditing(false);
    if (ended) {
      keep(null);
      onSaid({
        tone: "info",
        text: `Back to the preview: ${status.name} is no longer checked out.`,
      });
      return;
    }
    onSaid({
      tone: "warn",
      text: `Back to the preview. Your check-out couldn't be let go, so it holds until it runs out, or you check the file in.`,
      quiet: true,
    });
  };

  const lease = status.lease;
  // The lease names the reader's check-out while it holds, made in this tab or another.
  const leased = lease?.checkout_id ?? null;
  const reread = (refusal: number | null) => {
    void queryClient.invalidateQueries({
      queryKey: keys.files.status(tenant, workspace, artifact),
    });
    // A 409 may be the app switched off meanwhile: the workspace's switches are read again.
    if (refusal === 409) {
      void queryClient.invalidateQueries({
        queryKey: keys.grantr.enabledIntegrations(tenant, workspace),
      });
    }
  };
  /** Run a command, then read the file again. */
  const run = async <R,>(sent: Promise<Answer<R>>, undone: string): Promise<R | null> => {
    setPending(true);
    const answer = await sent;
    setPending(false);
    reread(answer.outcome === "done" ? null : answer.status);
    if (answer.outcome === "done") {
      return answer.result;
    }
    onSaid({ tone: "error", text: refused(undone, answer, app) });
    return null;
  };
  const checkOut = async () => {
    // The editor's place is asked for first: a file isn't held for an editor that can't open.
    if (here && !setEditing(true)) {
      return;
    }
    const checkout = await run(
      context.commands.files.checkOut(tenant, workspace, artifact),
      "It wasn't checked out",
    );
    if (checkout === null) {
      if (here) {
        setEditing(false);
      }
      return;
    }
    keep(checkout.id);
    const until = new Date(checkout.expires_at).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    if (here) {
      setBase(checkout.base_version);
      onSaid({
        tone: "info",
        text: `Checked out until ${until}. ${app} is opening here.`,
        quiet: flips,
      });
      return;
    }
    // Opened once it is checked out, while the click still counts. With `noopener` nothing says
    // whether a blocker took it, so "Open" stays beside the check-out, and the reader is told so.
    // The editor holds no handle on this window, nor this one on it (its `same-origin` policy).
    if (editor !== null) {
      window.open(editor, "_blank", "noopener,noreferrer");
    }
    const opened =
      editor === null ? "" : ` ${app} opened in a new tab: if it didn't, use "Open ${app}".`;
    onSaid({ tone: "info", text: `Checked out until ${until}, and downloading.${opened}` });
    await onDownload(checkout.base_version);
  };
  const extend = async (checkout: string) => {
    const extended = await run(
      context.commands.files.extend(tenant, workspace, checkout),
      "It wasn't extended",
    );
    if (extended !== null) {
      onSaid({ tone: "info", text: "Your check-out was extended." });
    }
  };
  const checkout = leased ?? own;
  if (checkout === null) {
    if (lease === null && flips && slots?.toggle) {
      return (
        <>
          {createPortal(
            <Button size="sm" disabled={pending} onClick={checkOut}>
              Edit in {app}
            </Button>,
            slots.toggle,
          )}
          <p className="text-muted text-sm">
            Editing checks it out, so no one else changes it meanwhile, and turns the preview into{" "}
            {app}, on a site of its own that can't see your session. When you save there, it is
            checked in; back to the preview, the check-out ends.
          </p>
        </>
      );
    }
    return lease === null ? (
      <div className="flex flex-col items-start gap-2">
        <Button disabled={pending} onClick={checkOut}>
          {here
            ? `Edit here in ${app}`
            : editor === null
              ? "Check out and download"
              : `Check out and open ${app}`}
        </Button>
        <p className="text-muted text-sm">
          {here
            ? `Editing checks it out, so no one else changes it meanwhile, and opens it in ${app} here, on a site of its own that can't see your session. When you save there, it is checked in, and your check-out ends.`
            : editor === null
              ? `Checking it out holds it for you and downloads it. No editor is hosted here: open it in ${app} yourself.`
              : `Checking it out holds it for you, downloads it, and opens ${app} in a new tab, on a site of its own that can't see your session. Open the downloaded file there.`}
        </p>
      </div>
    ) : null; // someone else's, or an agent's: who has it says so
  }
  const opened = base ?? status.version;
  const frame = here && editing && (
    <EditorFrame
      place={place}
      status={status}
      app={app}
      editor={editor}
      checkout={checkout}
      version={opened}
      flipped={flips}
      onSaid={onSaid}
      onEnded={() => {
        setEditing(false);
        keep(null);
      }}
      onAnswered={reread}
      onClose={() => (flips ? void release(checkout) : setEditing(false))}
    />
  );
  return (
    <div className="flex flex-col gap-3">
      {flips && slots?.viewport ? frame && createPortal(frame, slots.viewport) : frame}
      {flips &&
        slots?.toggle &&
        !editing &&
        createPortal(
          <Button size="sm" disabled={pending} onClick={() => setEditing(true)}>
            Edit in {app}
          </Button>,
          slots.toggle,
        )}
      <p className="text-sm">
        {lease !== null && leased !== null ? (
          <>
            It's yours until <Moment at={lease.expires_at} />.{" "}
          </>
        ) : (
          "Your check-out ran out. You can still check it in: if the file changed meanwhile, it becomes a proposal. "
        )}
        {here
          ? `Edit it in ${app} here, or save it to this computer from ${app} and check it in below.`
          : `Edit it in ${app}, save it to this computer, then check it in here.`}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {here && !editing && !flips && (
          <Button size="sm" disabled={pending} onClick={() => setEditing(true)}>
            Edit here in {app}
          </Button>
        )}
        {editor !== null && !here && (
          <TextLink href={editor} target="_blank" rel="noopener noreferrer">
            Open {app}
          </TextLink>
        )}
        <Button
          variant="secondary"
          size="sm"
          disabled={pending}
          onClick={() => void onDownload(status.version)}
        >
          Download again
        </Button>
        {leased !== null && (
          <Button
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => void extend(leased)}
          >
            Extend
          </Button>
        )}
      </div>
      <CheckIn
        key={checkout}
        place={place}
        status={status}
        app={app}
        checkout={checkout}
        onSaid={onSaid}
        onSending={() => keep(checkout)}
        onEnded={() => keep(null)}
        onAnswered={reread}
      />
    </div>
  );
}

/**
 * The edited file, chosen or dropped, sent with how far it has gone, stopped, and sent again
 * after an answer that never came. One button does each in turn, so focus stays on it.
 */
function CheckIn({
  place,
  status,
  app,
  checkout,
  onSaid,
  onSending,
  onEnded,
  onAnswered,
}: {
  place: Place;
  status: Status;
  app: string;
  checkout: string;
  onSaid: (said: Said | null) => void;
  /** Called as the file is sent: from then the check-out is kept, should its lease go meanwhile. */
  onSending: () => void;
  /** Called once the check-out has ended: checked in, or found checked in already. */
  onEnded: () => void;
  /** Called with a refusal's status, or null where it was done, for the file to be read again. */
  onAnswered: (refusal: number | null) => void;
}) {
  const { context, tenant, workspace } = place;
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState<{ sent: number; total: number } | null>(null);
  const [again, setAgain] = useState(false);
  // Whether the last answer never came: then the file may be in, and sending it again is safe.
  const lost = useRef(false);
  const stop = useRef<AbortController | null>(null);
  const extension = status.name.match(/\.[^.]+$/)?.[0];
  const tooLarge = file !== null && file.size > status.limit;
  const proposals = (lead: string) => (
    <>
      {lead}{" "}
      <TextLink
        render={<Link to="/t/$tenant/w/$workspace/proposals" params={{ tenant, workspace }} />}
      >
        the workspace's proposals
      </TextLink>
      .
    </>
  );
  const choose = (chosen: File) => {
    setFile(chosen);
    setAgain(false);
    lost.current = false;
    onSaid(
      chosen.size > status.limit
        ? {
            tone: "error",
            text: `${chosen.name} is ${fileSize(chosen.size)}: the largest file a check-in takes is ${fileSize(status.limit)}.`,
          }
        : null,
    );
  };
  const send = async (chosen: File) => {
    stop.current = new AbortController();
    onSending();
    onSaid(null);
    setSending({ sent: 0, total: chosen.size });
    const answer = await checkIn({
      surface: context.config.surfaces.artifactr,
      session: context.signed.session(),
      tenant,
      workspace,
      checkout,
      file: chosen,
      onProgress: (sent, total) => setSending({ sent, total }),
      signal: stop.current.signal,
      unsigned: () => void context.signed.signOut(),
    });
    setSending(null);
    onAnswered(answer.outcome === "done" ? null : answer.status);
    if (answer.outcome === "done") {
      const { result } = answer;
      const text = checkedIn(result, status.name, lost.current);
      setFile(null);
      onSaid(
        result.outcome === "proposed"
          ? { tone: "warn", text: proposals(text) }
          : { tone: "info", text },
      );
      onEnded();
      return;
    }
    if (answer.status === 409 && answer.type === "invalid_state" && lost.current) {
      // Sent again after a lost answer, and refused as checked in already: it is a proposal.
      onSaid({
        tone: "info",
        text: proposals(`${status.name} was checked in already, as a proposal: see`),
      });
      onEnded();
      return;
    }
    lost.current = answer.status === 0;
    setAgain(answer.status === 0 || answer.status === 503);
    onSaid({ tone: "error", text: refused("It wasn't checked in", answer, app) });
    // A check-out that is gone, someone else's, or checked in already takes no check-in again.
    if ([403, 404].includes(answer.status) || answer.type === "invalid_state") {
      onEnded();
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <FileChooser
        label="The edited file"
        hint={`The file you saved from ${app}, up to ${fileSize(status.limit)}.`}
        accept={extension}
        disabled={sending !== null}
        onFile={choose}
      />
      {file !== null && (
        <p role="status" className="text-sm">
          Chosen: <span className="break-all font-mono">{file.name}</span>, {fileSize(file.size)}
        </p>
      )}
      {sending !== null && file !== null && (
        <Progress
          label={`Checking in ${file.name}`}
          value={sending.sent}
          max={sending.total}
          valueText={`${fileSize(sending.sent)} of ${fileSize(sending.total)}`}
        />
      )}
      <Button
        className="self-start"
        variant={sending === null ? "primary" : "secondary"}
        disabled={sending === null && (file === null || tooLarge)}
        onClick={() => {
          if (sending !== null) {
            stop.current?.abort();
          } else if (file !== null) {
            void send(file);
          }
        }}
      >
        {sending !== null ? "Stop" : again ? "Try again" : "Check in"}
      </Button>
      <p className="text-muted text-sm">
        Your downloaded copy stays on this computer after you check it in: delete it if others use
        this computer.
      </p>
    </div>
  );
}
