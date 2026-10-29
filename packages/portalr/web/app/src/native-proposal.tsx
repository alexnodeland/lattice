/**
 * A proposal on a native file (lattice RFC-0003, portalr ADR-0050): an agent's edit by the app's
 * commands, or a person's check-in kept as a proposal because the file moved on meanwhile. Its
 * patch first tests the content it was made from, so one made against a version since replaced
 * can't be accepted, and says so: it is outdated, never rebased, and the agent plans again from
 * the head when asked. A reviewer compares its pages and words with the head's, on demand.
 */

import { type Artifactr, keys, Refused, usePeople } from "@portalr/client";
import { changes } from "@portalr/client/diff";
import {
  Alert,
  Button,
  Diff,
  Disclosure,
  fileSize,
  PageCompare,
  type PagePair,
  type PageShown,
  ProposalCard,
  type Sent,
  StatusBadge,
  usePhone,
} from "@portalr/ui";
import { type UseQueryResult, useQueries, useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import type { Place } from "./check-out";
import { fields, type Native } from "./native";
import { NativeChanges } from "./native-changes";
import { holderOf, PAGES_AT_ONCE, userOf } from "./native-file";
import { useWorkspace } from "./workspace";

type Op = Readonly<Record<string, unknown>>;

/** What a native file's proposal says of itself, read from its patch as `revise` builds it. */
export interface Proposed {
  /** The content digest it was made from, which its patch tests. */
  readonly tested: string | null;
  /** How its content was made: `commands` for an agent's, `check_in` for a person's. */
  readonly source: string | null;
  readonly pages: number | null;
  readonly size: number | null;
}

const record: (value: unknown) => Op = fields;

/** A native file's proposal, as its patch says, or null for a change that isn't one's patch. */
export function proposedOf(change: Artifactr.Proposal["change"]): Proposed | null {
  if (change?.type !== "edit_artifact" || change.patch.kind !== "json_patch") {
    return null;
  }
  const ops: readonly Op[] = change.patch.ops;
  const at = (op: string, path: string) =>
    ops.findLast((each) => each.op === op && each.path === path)?.value;
  const tested = at("test", "/content/sha256");
  const pages = at("replace", "/pages");
  const size = record(at("replace", "/content")).size;
  const source = record(at("replace", "/provenance")).source;
  return {
    tested: typeof tested === "string" ? tested : null,
    source: typeof source === "string" ? source : null,
    pages: typeof pages === "number" ? pages : null,
    size: typeof size === "number" ? size : null,
  };
}

/** How a native file's proposal was made, in words, from its provenance, if it says. */
function madeBy(proposed: Proposed | null, app: string): string | null {
  switch (proposed?.source) {
    case "check_in":
      return "A check-in kept as a proposal: the file changed after it was checked out.";
    case "commands":
      return `The agent's edit, by ${app}'s commands.`;
    default:
      return null;
  }
}

/** Why an outdated proposal can't be accepted, and what to do instead, by who made it. */
function outdatedBy(proposed: Proposed, version: number): string {
  const instead =
    proposed.source === "check_in"
      ? `Reject it, check the file out again from version ${version}, and make the change there.`
      : `Reject it, and ask the agent again: it plans again from version ${version}.`;
  return `Outdated: it was made against a version of the file since replaced, so accepting it would fail. ${instead}`;
}

/**
 * A native file's proposal, as a `ProposalCard`: how it was made, and while it is open, whether
 * it is outdated, who has the file now, and its pages and words beside the head's, when asked. A
 * resolved one reads nothing more.
 */
export function NativeProposal({
  place,
  native,
  me,
  proposal,
  onRespond,
  id,
  children,
}: {
  /** Its id in the page, to link to, as `ProposalCard`'s. */
  id?: string;
  /** Where it is shown, and the file it would change. */
  place: Place;
  native: Native;
  me: string;
  proposal: Artifactr.Proposal;
  onRespond: (decision: "accept" | "reject") => Sent;
  /** More about it, such as a link to the file. */
  children?: ReactNode;
}) {
  const proposed = proposedOf(proposal.change);
  const made = madeBy(proposed, native.app);
  if (proposal.status !== "open" || proposed === null) {
    return (
      <ProposalCard id={id} proposal={proposal} onRespond={onRespond}>
        {children}
        {made && <p className="text-sm">{made}</p>}
      </ProposalCard>
    );
  }
  return (
    <OpenProposal
      id={id}
      place={place}
      me={me}
      proposal={proposal}
      proposed={proposed}
      app={native.app}
      onRespond={onRespond}
    >
      {children}
      {made && <p className="text-sm">{made}</p>}
    </OpenProposal>
  );
}

function OpenProposal({
  id,
  place,
  me,
  proposal,
  proposed,
  app,
  onRespond,
  children,
}: {
  id: string | undefined;
  place: Place;
  me: string;
  proposal: Artifactr.Proposal;
  proposed: Proposed;
  app: string;
  onRespond: (decision: "accept" | "reject") => Sent;
  children: ReactNode;
}) {
  const { context, tenant, workspace, artifact } = place;
  const { queries, queryClient, config } = context;
  const { data: revisions } = useQuery(queries.artifactr.revisions(tenant, workspace, artifact));
  const { data: status } = useQuery(queries.files.status(tenant, workspace, artifact));
  const holder = userOf(status?.lease);
  const names = usePeople(queries, config.people, tenant, holder === undefined ? [] : [holder]);
  // The head as read over REST, and the version the workspace's log has reached: where the log is
  // ahead, as after a reconnect's replay, the revisions are read again before anything is said.
  const read = revisions?.at(-1);
  const logged = useWorkspace().state.artifacts[artifact]?.version;
  const behind = read !== undefined && logged !== undefined && logged > read.version;
  useEffect(() => {
    if (behind) {
      void queryClient.invalidateQueries({
        queryKey: keys.artifactr.revisions(tenant, workspace, artifact),
      });
    }
  }, [behind, queryClient, tenant, workspace, artifact]);
  const head = behind ? undefined : read;
  const outdated =
    head !== undefined &&
    proposed.tested !== null &&
    proposed.tested !== record(head.data.content).sha256;
  const held = status ? holderOf(status.lease, me, names) : null;
  const pages = head?.data.pages;
  const compare: Compare | undefined = head && {
    place,
    proposal: proposal.id,
    version: head.version,
    pages: { head: typeof pages === "number" ? pages : null, proposed: proposed.pages },
    app,
    commands: proposed.source !== "check_in",
  };
  return (
    <ProposalCard
      id={id}
      proposal={proposal}
      onRespond={onRespond}
      blocked={outdated && head !== undefined ? outdatedBy(proposed, head.version) : null}
    >
      {outdated && (
        <StatusBadge tone="stopped" className="self-start">
          Outdated
        </StatusBadge>
      )}
      {proposed.source !== "check_in" && (
        <NativeChanges
          place={place}
          proposal={proposal.id}
          preview={compare && <BeforeAfter {...compare} />}
        />
      )}
      {children}
      {(held?.kind === "person" || held?.kind === "you") && (
        <Alert tone="warn" live={false}>
          {held.kind === "you"
            ? "You have the file checked out: accepting this now makes your check-in a proposal in turn."
            : `${held.who} has the file checked out: accepting this now makes their check-in a proposal in turn.`}
        </Alert>
      )}
      {compare && <Comparison {...compare} size={proposed.size} />}
    </ProposalCard>
  );
}

/** Where a proposal's pages are compared: its file, and how many pages each side has. */
interface Compare {
  readonly place: Place;
  readonly proposal: string;
  readonly version: number;
  readonly pages: { readonly head: number | null; readonly proposed: number | null };
  /** The file's app, as people call it. */
  readonly app: string;
  /** Whether it was made by commands, which may name the pages they change. */
  readonly commands: boolean;
}

/** The apps whose CLI draws no page (native files ADR-0020): their changes are said in words. */
const NO_PICTURE = new Set(["GridCraft", "SoundCraft"]);

/**
 * The proposal's words and pages beside the head's: open at first on a desktop, on the first
 * changed page, and read only once open.
 */
function Comparison(props: Compare & { size: number | null }) {
  const phone = usePhone();
  const [open, setOpen] = useState(!phone);
  return (
    <Disclosure
      look="link"
      summary={`Compare with version ${props.version}${props.size === null ? "" : ` (proposed: ${fileSize(props.size)})`}`}
      open={open}
      onOpenChange={setOpen}
      className="text-sm"
    >
      {open && <Compared {...props} />}
    </Disclosure>
  );
}

function Compared(props: Compare) {
  const { place, proposal, version } = props;
  const { context, tenant, workspace, artifact } = place;
  const { queries } = context;
  // None: the first changed page alone; then as many from the first as were asked for.
  const [shown, setShown] = useState(0);
  const [was, is] = useQueries({
    queries: [
      queries.files.text(tenant, workspace, artifact, version),
      queries.files.proposedText(tenant, workspace, proposal),
    ],
  });
  const words = useMemo(
    () =>
      typeof was?.data === "string" && typeof is?.data === "string"
        ? changes(was.data, is.data, "words")
        : undefined,
    [was?.data, is?.data],
  );
  const most = Math.max(props.pages.head ?? 0, props.pages.proposed ?? 0);
  return (
    <div className="flex flex-col gap-3 pt-2">
      <p className="font-semibold">Its words</p>
      {words === undefined ? (
        <p className="text-muted">
          {was?.isError || is?.isError
            ? "Its words couldn't be read."
            : was?.data === null || is?.data === null
              ? "The app read no words from one of these versions."
              : "Reading its words…"}
        </p>
      ) : (
        <Diff changes={words} />
      )}
      <BeforeAfter {...props} shown={shown} />
      {!NO_PICTURE.has(props.app) && (shown || 1) < most && (
        <Button
          variant="secondary"
          size="sm"
          className="self-start"
          onClick={() => setShown((before) => before + PAGES_AT_ONCE)}
        >
          Compare more pages
        </Button>
      )}
    </div>
  );
}

/**
 * How a page that couldn't be drawn is shown: why, in words, never the server's, and where asking
 * again may draw it, a retry.
 */
function failed(page: number, read: UseQueryResult<string>, proposed: boolean): PageShown {
  const { error } = read;
  const retry = () => void read.refetch();
  if (!(error instanceof Refused)) {
    return { page, state: "failed", onRetry: retry };
  }
  if (error.status === 429 || error.status === 503) {
    const said = `Still preparing the picture. Try again in ${error.retryAfter ?? 10} seconds.`;
    return { page, state: "failed", said, onRetry: retry };
  }
  return proposed && record(record(error.detail).detail).reason === "content_unavailable"
    ? { page, state: "failed", said: "The proposed file isn't stored." }
    : { page, state: "failed", onRetry: retry };
}

/**
 * The proposal's pages beside the head's: the first that changed alone, as its commands name it
 * or as the pages read say, or `shown` pages from the first; where its app draws none, that said.
 */
export function BeforeAfter({
  place,
  proposal,
  version,
  pages,
  app,
  commands,
  shown = 0,
}: Compare & { shown?: number }) {
  const { context, tenant, workspace, artifact } = place;
  const { queries } = context;
  const { data: said } = useQuery({
    ...queries.files.proposedCommands(tenant, workspace, proposal),
    enabled: commands,
  });
  const drawn = !NO_PICTURE.has(app);
  const most = drawn ? Math.max(pages.head ?? 0, pages.proposed ?? 0) : 0;
  const named = said?.items.flatMap((item) => item.pages) ?? [];
  // Where no command names a page, the first is looked at, then each after it that reads the same.
  const [at, setAt] = useState(1);
  const numbers = shown
    ? Array.from({ length: Math.min(shown, most) }, (_, index) => index + 1)
    : most > 0
      ? [Math.min(named.length > 0 ? Math.min(...named) : at, most)]
      : [];
  const has = (total: number | null, page: number) => total !== null && page <= total;
  // A page the app is too busy or slow to draw is said at once, with a retry, not waited on.
  const heads = useQueries({
    queries: numbers.map((page) => ({
      ...queries.files.page(tenant, workspace, artifact, version, page),
      enabled: has(pages.head, page),
      retry: false,
    })),
  });
  const theirs = useQueries({
    queries: numbers.map((page) => ({
      ...queries.files.proposedPage(tenant, workspace, proposal, page),
      enabled: has(pages.proposed, page),
      retry: false,
    })),
  });
  const same = !shown && named.length === 0 && heads[0]?.data === theirs[0]?.data;
  useEffect(() => {
    if (same && heads[0]?.data !== undefined && at < Math.min(most, PAGES_AT_ONCE)) {
      setAt(at + 1);
    }
  });
  if (!drawn) {
    return (
      <p className="text-muted">
        {app} can't show a picture of this change. Its words and commands are listed above.
      </p>
    );
  }
  const side = (read: UseQueryResult<string> | undefined, page: number, proposed: boolean) =>
    read === undefined
      ? null
      : read.data !== undefined
        ? { page, src: read.data }
        : read.isError
          ? failed(page, read, proposed)
          : { page, state: "reading" as const };
  const pairs = numbers.map(
    (page, index): PagePair => ({
      page,
      before: has(pages.head, page) ? side(heads[index], page, false) : null,
      after: has(pages.proposed, page) ? side(theirs[index], page, true) : null,
    }),
  );
  return (
    <>
      <p role="status" className="text-muted">
        {[...heads, ...theirs].some((read) => read.isFetching)
          ? "Preparing the pictures of its pages…"
          : ""}
      </p>
      {pairs.length > 0 && (
        <PageCompare
          label="Its pages beside the head's"
          before={`Version ${version}`}
          after="Proposed"
          pages={pairs}
        />
      )}
    </>
  );
}
