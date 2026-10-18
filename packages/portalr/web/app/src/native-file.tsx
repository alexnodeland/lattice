/**
 * A native file on its artifact's page (portalr ADR-0048): who has it, its pages, a download, and
 * what each revision changed in its words. Every read goes through native files' routes, as the
 * signed-in person: a page is shown as a `data:` URL, and a download is saved from a `Blob`, so
 * the app's policy gains nothing for either.
 */

import {
  changes,
  type createQueries,
  type FilesApi,
  type IntegrationKey,
  type Names,
  Refused,
  useEnabled,
  usePeople,
} from "@portalr/client";
import {
  Alert,
  Button,
  Diff,
  FileHolder,
  type Holder,
  type PageShown,
  PageStrip,
  SectionTitle,
} from "@portalr/ui";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";

type Queries = ReturnType<typeof createQueries>;
type Lease = FilesApi.components["schemas"]["Lease"];

/** A native file's app: what people call it, and the integration that switches it. */
export interface Native {
  readonly app: string;
  readonly integration: IntegrationKey;
}

/** How many pages are shown at first, and how many more each time more are asked for. */
const PAGES_AT_ONCE = 4;

/** The user a lease's check-out is a person's, by their id, if it is a person's. */
const userOf = (lease: Lease | null | undefined): string | undefined =>
  lease?.checked_out_by?.match(/^user:(.+)$/s)?.[1];

/**
 * Who has a file, as the reader reads it: their own check-out, someone else's by name, or an
 * agent's edit, which names no one.
 */
export function holderOf(lease: Lease | null, me: string, names: Names): Holder {
  if (lease === null) {
    return { kind: "free" };
  }
  if (lease.checked_out_by === null) {
    return { kind: "agent" };
  }
  const user = userOf(lease);
  if (user === me) {
    return { kind: "you", until: lease.expires_at };
  }
  // Another participant, such as an external agent's client, by what follows its kind.
  const who = user === undefined ? lease.checked_out_by.replace(/^[^:]*:/, "") : names(user);
  return { kind: "person", who, until: lease.expires_at };
}

/** A manifest's text blob's digest, if it names one. */
const textOf = (data: Readonly<Record<string, unknown>>): string | null => {
  const text = data.text;
  return typeof text === "object" && text !== null && "sha256" in text ? String(text.sha256) : null;
};

/** Whether a revision changed a native file's words: both versions have text, and it differs. */
export function wordsChanged(
  before: Readonly<Record<string, unknown>>,
  after: Readonly<Record<string, unknown>>,
): boolean {
  const [was, is] = [textOf(before), textOf(after)];
  return was !== null && is !== null && was !== is;
}

/** Save bytes as a file of a name, as a download the browser asks where to put. */
function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  // Kept a while after the click, which some browsers read from after it returns.
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/**
 * A native file's own section: who has it, a download of its head, its pages, a few at a time,
 * and, where its app is off in the workspace, that it is only read here. Where its routes aren't
 * served, there is no section: the manifest above is all there is.
 */
export function NativeFile({
  queries,
  tenant,
  workspace,
  artifact,
  native,
  me,
  people,
}: {
  queries: Queries;
  tenant: string;
  workspace: string;
  artifact: string;
  /** The file's app, by its name and the integration that switches it. */
  native: Native;
  /** The reader's user id. */
  me: string;
  /** Whether the server names people, by their emails. */
  people: boolean;
}) {
  const heading = useId();
  const queryClient = useQueryClient();
  const enabled = useEnabled(queries, tenant, workspace);
  const { data: status, error } = useQuery(queries.files.status(tenant, workspace, artifact));
  const holder = userOf(status?.lease);
  const names = usePeople(queries, people, tenant, holder === undefined ? [] : [holder]);
  const [shown, setShown] = useState(PAGES_AT_ONCE);
  const [saving, setSaving] = useState<"saving" | "failed" | null>(null);
  const total = status?.pages ?? 0;
  const numbers = Array.from({ length: Math.min(shown, total) }, (_, index) => index + 1);
  const pages = useQueries({
    queries: numbers.map((page) =>
      queries.files.page(tenant, workspace, artifact, status?.version ?? 1, page),
    ),
  });
  if (error instanceof Refused && error.status === 404) {
    return null;
  }
  const title = <SectionTitle id={heading}>The file</SectionTitle>;
  if (status === undefined) {
    // Unread, or refused before it was ever read: a refusal later keeps what was read.
    return error === null ? null : (
      <section aria-labelledby={heading} className="flex flex-col gap-3">
        {title}
        <Alert tone="error">
          The file's status couldn't be read: who has it, and its pages. Reload the page to try
          again.
        </Alert>
      </section>
    );
  }
  const download = async () => {
    setSaving("saving");
    try {
      save(
        await queryClient.fetchQuery(
          queries.files.content(tenant, workspace, artifact, status.version),
        ),
        status.name,
      );
      setSaving(null);
    } catch {
      setSaving("failed");
    }
  };
  const on = status.enabled && enabled(native.integration);
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Button variant="secondary" disabled={saving === "saving"} onClick={download}>
          {saving === "saving" ? "Downloading…" : "Download"}
        </Button>
      </div>
      {on ? (
        <FileHolder holder={holderOf(status.lease, me, names)} />
      ) : (
        <Alert>
          {native.app} is off in this workspace: you can read and download this file, but not check
          it out, and the agent can't edit it.
        </Alert>
      )}
      {saving === "failed" && (
        <Alert tone="error">The file wasn't downloaded. Try again in a moment.</Alert>
      )}
      {total > 0 && (
        <PageStrip
          label={`Pages of version ${status.version}`}
          pages={numbers.map((page, index): PageShown => {
            const read = pages[index];
            return read?.data !== undefined
              ? { page, src: read.data }
              : { page, state: read?.isError ? "failed" : "reading" };
          })}
          total={total}
          onMore={() => setShown((before) => before + PAGES_AT_ONCE)}
        />
      )}
    </section>
  );
}

/**
 * What a revision changed in a native file's words, from the text the app read from it and from
 * the revision before it, compared word by word only when asked: each side is a read, and the
 * comparison can take a moment.
 */
export function TextChanges({
  queries,
  tenant,
  workspace,
  artifact,
  versions,
}: {
  queries: Queries;
  tenant: string;
  workspace: string;
  artifact: string;
  /** The revision before, and the revision. */
  versions: readonly [number, number];
}) {
  const [open, setOpen] = useState(false);
  return (
    <details className="text-sm" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-accent underline-offset-2 hover:underline">
        Changes to its words
      </summary>
      {open && (
        <Compared
          queries={queries}
          tenant={tenant}
          workspace={workspace}
          artifact={artifact}
          versions={versions}
        />
      )}
    </details>
  );
}

function Compared({
  queries,
  tenant,
  workspace,
  artifact,
  versions,
}: {
  queries: Queries;
  tenant: string;
  workspace: string;
  artifact: string;
  versions: readonly [number, number];
}) {
  const [before, after] = useQueries({
    queries: versions.map((each) => queries.files.text(tenant, workspace, artifact, each)),
  });
  const [was, is] = [before?.data, after?.data];
  // Compared once for each pair of texts, not on every event the page's stream brings.
  const changed = useMemo(
    () => (typeof was === "string" && typeof is === "string" ? changes(was, is, "words") : null),
    [was, is],
  );
  if (before?.isError || after?.isError) {
    return <p className="pt-2 text-muted">Its words couldn't be read.</p>;
  }
  if (was === undefined || is === undefined) {
    return <p className="pt-2 text-muted">Reading its words…</p>;
  }
  if (was === null || is === null) {
    return <p className="pt-2 text-muted">The app read no words from one of these versions.</p>;
  }
  return <Diff changes={changed} className="pt-2" />;
}
