/**
 * A workspace's artifactr stream, open while the workspace's routes are, and its store for the
 * routes under it: its threads, messages, runs and proposals, as the log builds them, and where
 * the connection is.
 */

import {
  type Artifactr,
  type ArtifactrStream,
  artifactr,
  type Snapshot,
  Stream,
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
import type { Signed } from "./signed";

const Current = createContext<ArtifactrStream | null>(null);

/**
 * Open the workspace's stream for what is inside, and close it when they go. It connects again
 * with each refreshed token, and closes when the session ends.
 */
export function WorkspaceStream({
  surface,
  signed,
  tenant,
  workspace,
  children,
}: {
  /** artifactr's surface, from `config.json`, which may be a path on this origin. */
  surface: string;
  signed: Signed;
  tenant: string;
  workspace: string;
  children: ReactNode;
}) {
  const [stream] = useState(
    () =>
      new Stream(artifactr, {
        url: () =>
          streamUrl(
            new URL(surface, location.origin).href,
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

/** The workspace's stream, to send commands on. */
export function useStream(): ArtifactrStream {
  const stream = useContext(Current);
  if (stream === null) {
    throw new Error("useStream is for routes inside a workspace");
  }
  return stream;
}

/** The workspace as its log has built it so far, and the connection's state, rendered as they change. */
export function useWorkspace(): Snapshot<Artifactr.Workspace> {
  const stream = useStream();
  return useSyncExternalStore(stream.subscribe, stream.snapshot);
}

/**
 * What a workspace's area shows before its log has been read, or once its connection has ended:
 * `null` when it is live, or still has its log to show.
 */
export function Connection({
  snapshot,
  waiting,
}: {
  snapshot: Snapshot<Artifactr.Workspace>;
  /** What is being read, such as "the workspace". */
  waiting: string;
}) {
  if (snapshot.status === "closed") {
    return (
      <p role="alert">
        The connection to this workspace ended{snapshot.error ? `: ${snapshot.error}` : ""}. Reload
        the page to connect again.
      </p>
    );
  }
  if (snapshot.status !== "live") {
    return <p role="status">Reading {waiting}…</p>;
  }
  return null;
}
