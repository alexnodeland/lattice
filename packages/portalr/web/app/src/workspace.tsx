/**
 * A workspace's streams, open while the workspace's routes are: artifactr's, whose store holds
 * its threads, messages, artifacts, proposals and turns, and reflexr's, whose store holds its
 * rules and runs. The routes under it read either store, and where its connection is; and what
 * either log says changed, once live, makes stale the reads it changed (`client`'s `stale`), as
 * does a command artifactr refuses as `not_enabled`, which makes the workspace's integrations
 * stale. Those integrations say which add-ons the Markdown inside may draw (portalr ADR-0045).
 */

import {
  type Artifactr,
  type ArtifactrStream,
  artifactr,
  type createQueries,
  type Reflexr,
  type ReflexrStream,
  reflexr,
  type Signed,
  type Snapshot,
  Stream,
  type Surfaces,
  stale,
  streamUrl,
  useEnabled,
} from "@portalr/client";
import { AddonsProvider, Alert, Reading } from "@portalr/ui";
import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
} from "react";

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
  const queryClient = useQueryClient();
  useEffect(() => {
    const invalidate = (keys: readonly (readonly unknown[])[]) => {
      for (const queryKey of keys) {
        void queryClient.invalidateQueries({ queryKey });
      }
    };
    const unhear = [
      streams.artifactr.onLiveEvent((envelope) =>
        invalidate(stale.artifactr(tenant, workspace, envelope)),
      ),
      streams.reflexr.onLiveEvent((envelope) =>
        invalidate(stale.reflexr(tenant, workspace, envelope)),
      ),
      streams.artifactr.onRefused((result) => invalidate(stale.refusal(tenant, workspace, result))),
    ];
    return () => {
      for (const stop of unhear) {
        stop();
      }
    };
  }, [streams, queryClient, tenant, workspace]);
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

/**
 * The add-ons the Markdown inside may draw, from the workspace's integrations: each its default
 * until they are read, and where they can't be, so Mermaid stays off.
 */
export function WorkspaceAddons({
  queries,
  tenant,
  workspace,
  children,
}: {
  queries: ReturnType<typeof createQueries>;
  tenant: string;
  workspace: string;
  children: ReactNode;
}) {
  const enabled = useEnabled(queries, tenant, workspace);
  return (
    <AddonsProvider
      value={{ math: enabled("markdown:math"), mermaid: enabled("markdown:mermaid") }}
    >
      {children}
    </AddonsProvider>
  );
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
      <Alert tone="error">
        The connection to this workspace ended{snapshot.error ? `: ${snapshot.error}` : ""}. Reload
        the page to connect again.
      </Alert>
    );
  }
  if (snapshot.status !== "live") {
    return <Reading>Reading {waiting}…</Reading>;
  }
  return null;
}
