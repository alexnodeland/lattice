/**
 * A native file's parts as the app's pages place them, each drawn by the native files' add-on,
 * `on-demand/files` (portalr ADR-0044), loaded the first time a page shows one. A file's section
 * reads its status as the add-on loads, not after, so the two come together. While it loads, the
 * place says so; where it won't, why, with a way to try again. A revision's words say nothing
 * either way: the file's section says it once for the page.
 */

import { Button, FailureAlert, Reading, retry, useLoaded } from "@portalr/ui";
import { usePrefetchQuery } from "@tanstack/react-query";
import type { ComponentProps, ReactNode } from "react";

const loadFiles = () => import("./on-demand/files");

type Files = Awaited<ReturnType<typeof loadFiles>>;

/**
 * What `draw` draws once the add-on has loaded; `loading` until it has; and, where it won't, why,
 * and a way to try again, or nothing where the part is `quiet`.
 */
function WithFiles({
  loading,
  draw,
  quiet = false,
}: {
  loading: ReactNode;
  draw: (files: Files) => ReactNode;
  quiet?: boolean;
}) {
  const { module: files, failed, error } = useLoaded(loadFiles);
  if (failed) {
    return quiet ? null : (
      <div className="flex flex-col items-start gap-2">
        <FailureAlert error={error} />
        <Button variant="secondary" size="sm" onClick={() => retry(loadFiles)}>
          Try again
        </Button>
      </div>
    );
  }
  return files === null ? loading : draw(files);
}

export function NativeFile(props: ComponentProps<Files["NativeFile"]>) {
  const { context, tenant, workspace, artifact } = props.place;
  usePrefetchQuery(context.queries.files.status(tenant, workspace, artifact));
  return (
    <WithFiles
      loading={<Reading>Loading the file…</Reading>}
      draw={(files) => <files.NativeFile {...props} />}
    />
  );
}

export const NativeInline = (props: ComponentProps<Files["NativeInline"]>) => (
  <WithFiles
    loading={<Reading>Loading the file…</Reading>}
    draw={(files) => <files.NativeInline {...props} />}
  />
);

export const NativeProposal = (props: ComponentProps<Files["NativeProposal"]>) => (
  <WithFiles
    loading={<Reading>Loading the proposal…</Reading>}
    draw={(files) => <files.NativeProposal {...props} />}
  />
);

/** A revision's words, offered once the add-on has loaded: nothing is drawn until then. */
export const TextChanges = (props: ComponentProps<Files["TextChanges"]>) => (
  <WithFiles quiet loading={null} draw={(files) => <files.TextChanges {...props} />} />
);
