/**
 * A workspace's artifactr stream, open while the workspace's routes are, and its store for the
 * routes under it: its threads, messages, runs and proposals, as the log builds them.
 */

import {
  type Artifactr,
  type ArtifactrStream,
  artifactr,
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

/** Open the workspace's stream for what is inside, and close it when they go. */
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
    return () => stream.close();
  }, [stream]);
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

/** The workspace as its log has built it so far, rendered again as it changes. */
export function useWorkspace(): Artifactr.Workspace {
  const stream = useStream();
  return useSyncExternalStore(stream.subscribe, stream.snapshot).state;
}
