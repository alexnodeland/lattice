/**
 * A workspace's streams, open while the workspace's routes are: artifactr's, whose store holds
 * its threads, messages, artifacts, proposals and turns, and reflexr's, whose store holds its
 * rules and runs. The routes under it read either store, and where its connection is.
 */

import {
  type Artifactr,
  type ArtifactrStream,
  artifactr,
  type Reflexr,
  type ReflexrStream,
  reflexr,
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
import type { Signed } from "./signed";

interface Streams {
  readonly artifactr: ArtifactrStream;
  readonly reflexr: ReflexrStream;
}

const Current = createContext<Streams | null>(null);

/**
 * Open the workspace's streams for what is inside, and close them when they go. Each connects
 * again with each refreshed token, and closes when the session ends.
 */
export function WorkspaceStreams({
  surfaces,
  signed,
  tenant,
  workspace,
  children,
}: {
  /** The libraries' surfaces, from `config.json`, which may be paths on this origin. */
  surfaces: Surfaces;
  signed: Signed;
  tenant: string;
  workspace: string;
  children: ReactNode;
}) {
  const [streams] = useState<Streams>(() => {
    const url = (surface: string) => () =>
      streamUrl(new URL(surface, location.origin).href, workspace, signed.streamSession(tenant));
    return {
      artifactr: new Stream(artifactr, { url: url(surfaces.artifactr) }),
      reflexr: new Stream(reflexr, { url: url(surfaces.reflexr) }),
    };
  });
  useEffect(() => {
    const each = [streams.artifactr, streams.reflexr];
    for (const stream of each) {
      stream.open();
    }
    const unwatch = signed.watch((change) => {
      for (const stream of each) {
        change === "refreshed" ? stream.reconnect() : stream.close();
      }
    });
    return () => {
      unwatch();
      for (const stream of each) {
        stream.close();
      }
    };
  }, [streams, signed]);
  return <Current value={streams}>{children}</Current>;
}

function useStreams(): Streams {
  const streams = useContext(Current);
  if (streams === null) {
    throw new Error("a workspace's streams are for routes inside a workspace");
  }
  return streams;
}

/** artifactr's stream, to send commands on. */
export function useStream(): ArtifactrStream {
  return useStreams().artifactr;
}

/** reflexr's stream, to send commands on. */
export function useAutomationStream(): ReflexrStream {
  return useStreams().reflexr;
}

/** The workspace as artifactr's log has built it so far, and the connection, as they change. */
export function useWorkspace(): Snapshot<Artifactr.Workspace> {
  const stream = useStream();
  return useSyncExternalStore(stream.subscribe, stream.snapshot);
}

/** The workspace's rules and runs as reflexr's log has built them, and the connection. */
export function useAutomation(): Snapshot<Reflexr.Workspace> {
  const stream = useAutomationStream();
  return useSyncExternalStore(stream.subscribe, stream.snapshot);
}

/**
 * What a workspace's area shows before a log has been read, or once its connection has ended:
 * nothing when it is live.
 */
export function Connection({
  snapshot,
  waiting,
}: {
  snapshot: Snapshot<unknown>;
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
