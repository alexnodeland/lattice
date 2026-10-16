/**
 * A workspace's rule runs, as reflexr's stream builds them, open while Runs shows that workspace
 * (portalr ADR-0032). One stream, for the one workspace chosen: it opens with the page, reconnects
 * with each refreshed token and from where it was after a drop, closes when the session ends, and
 * closes when the page does or another workspace is chosen. It asks for the run events alone, so
 * the bodies of the application's events never reach the browser.
 */

import {
  type Reflexr,
  type ReflexrStream,
  RUN_EVENTS,
  reflexr,
  type Signed,
  type Snapshot,
  Stream,
  type Surfaces,
  streamUrl,
} from "@portalr/client";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
} from "react";

const Current = createContext<ReflexrStream | null>(null);

interface Props {
  surfaces: Surfaces;
  signed: Signed;
  tenant: string;
  workspace: string;
  children: ReactNode;
}

/**
 * The stream for a tenant's workspace, and what is inside it. Another tenant or workspace is
 * another stream, made new, whoever renders this: it is keyed by both here, so it does not depend
 * on a caller's key to keep one workspace's stream and state from another's.
 */
export function RunStreams(props: Props) {
  return <Open key={`${props.tenant}:${props.workspace}`} {...props} />;
}

function Open({ surfaces, signed, tenant, workspace, children }: Props) {
  const [stream] = useState(
    () =>
      new Stream(reflexr, {
        url: () =>
          streamUrl(
            new URL(surfaces.reflexr, location.origin).href,
            workspace,
            signed.streamSession(tenant),
          ),
        hello: { types: [...RUN_EVENTS] },
      }),
  );
  useEffect(() => {
    stream.open();
    const unwatch = signed.watch((change) =>
      change === "refreshed" ? stream.reconnect() : stream.close(),
    );
    return () => {
      unwatch();
      stream.close();
    };
  }, [stream, signed]);
  return <Current value={stream}>{children}</Current>;
}

function useRunStream(): ReflexrStream {
  const stream = useContext(Current);
  if (stream === null) {
    throw new Error("rule runs are read inside a workspace's stream");
  }
  return stream;
}

/** The workspace's runs as reflexr's log has built them so far, and the connection. */
export function useRuns(): Snapshot<Reflexr.Workspace> {
  const stream = useRunStream();
  return useSyncExternalStore(stream.subscribe, stream.snapshot);
}

/** A command, as the stream sends it. */
type Command = Parameters<ReflexrStream["send"]>[0];

/**
 * Carries out commands on the stream, once each, as a person confirmed them.
 *
 * A command is sent with an id of its own, which lasts as long as the dialog that asked for it is
 * open: if the connection ends before the server answers, the same id is sent when the person
 * tries again in that dialog, and the server carries it out once. Any answer ends the id, and so
 * does `release`, which is called when the dialog closes, however it closes: a later intention is
 * a new command under a new id, never one the server may answer from an earlier time. `send`
 * throws what the person should be told.
 */
export function useAct(
  refused: (rejection: { readonly [key: string]: unknown } | null | undefined) => string,
) {
  const stream = useRunStream();
  const [ids] = useState(() => new Map<string, string>());
  const keyOf = (command: Command) =>
    `${command.type}:${"run_id" in command ? command.run_id : ""}`;
  return {
    async send(command: Command) {
      const key = keyOf(command);
      const id = ids.get(key) ?? crypto.randomUUID();
      ids.set(key, id);
      const settled = await stream.send(command, id);
      if (settled.outcome === "closed") {
        throw new Error(
          "The connection ended before the server answered. Try again: it is carried out once.",
        );
      }
      ids.delete(key);
      if (settled.outcome === "refused") {
        throw new Error(refused(settled.result.rejection));
      }
    },
    /** The dialog for this command closed: its id is of that intention alone. */
    release(command: Command) {
      ids.delete(keyOf(command));
    },
  };
}
