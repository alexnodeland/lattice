/**
 * A workspace's rule runs, as reflexr's stream builds them, open while Runs shows that workspace
 * (portalr ADR-0032). One stream, for the one workspace chosen: it opens with the page, reconnects
 * with each refreshed token and from where it was after a drop, closes when the session ends, and
 * closes when the page does or another workspace is chosen, which is another page, with a stream
 * of its own.
 */

import {
  type Reflexr,
  type ReflexrStream,
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

export function RunStreams({
  surfaces,
  signed,
  tenant,
  workspace,
  children,
}: {
  surfaces: Surfaces;
  signed: Signed;
  tenant: string;
  workspace: string;
  children: ReactNode;
}) {
  const [stream] = useState(
    () =>
      new Stream(reflexr, {
        url: () =>
          streamUrl(
            new URL(surfaces.reflexr, location.origin).href,
            workspace,
            signed.streamSession(tenant),
          ),
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

/** reflexr's stream for the workspace shown, to send commands on. */
function useRunStream(): ReflexrStream {
  const stream = useContext(Current);
  if (stream === null) {
    throw new Error("rule runs are read inside a workspace's stream");
  }
  return stream;
}

/** The workspace's rules and runs as reflexr's log has built them so far, and the connection. */
export function useRuns(): Snapshot<Reflexr.Workspace> {
  const stream = useRunStream();
  return useSyncExternalStore(stream.subscribe, stream.snapshot);
}

/**
 * Carries out a command on the stream, once, as the person confirmed it: each command is sent
 * with an id of its own, and if the connection ends before the server answers, it is the same id
 * that is sent when the person tries again, which the server carries out once. A refusal, or an
 * answer of any kind, ends that id. It throws what the person should be told.
 */
export function useAct(
  refused: (rejection: { readonly [key: string]: unknown } | null | undefined) => string,
) {
  const stream = useRunStream();
  const [ids] = useState(() => new Map<string, string>());
  return async (command: Parameters<ReflexrStream["send"]>[0]) => {
    const key = JSON.stringify(command);
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
  };
}
