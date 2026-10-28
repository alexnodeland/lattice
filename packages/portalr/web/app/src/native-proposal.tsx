/**
 * A proposal on a native file (lattice RFC-0003, portalr ADR-0050): an agent's edit by the app's
 * commands, or a person's check-in kept as a proposal because the file moved on meanwhile. Its
 * patch first tests the content it was made from, so one made against a version since replaced
 * can't be accepted, and says so: it is outdated, never rebased, and the agent plans again from
 * the head when asked. A reviewer compares its pages and words with the head's, on demand.
 */

import { type Artifactr, keys, usePeople } from "@portalr/client";
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
  onRespond,
  children,
}: {
  id: string | undefined;
  place: Place;
  me: string;
  proposal: Artifactr.Proposal;
  proposed: Proposed;
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
  const pages = head === undefined ? undefined : head.data.pages;
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
      <NativeChanges place={place} proposal={proposal.id} />
      {children}
      {(held?.kind === "person" || held?.kind === "you") && (
        <Alert tone="warn" live={false}>
          {held.kind === "you"
            ? "You have the file checked out: accepting this now makes your check-in a proposal in turn."
            : `${held.who} has the file checked out: accepting this now makes their check-in a proposal in turn.`}
        </Alert>
      )}
      {head !== undefined && (
        <Comparison
          place={place}
          proposal={proposal.id}
          version={head.version}
          pages={{
            head: typeof pages === "number" ? pages : null,
            proposed: proposed.pages,
          }}
          size={proposed.size}
        />
      )}
    </ProposalCard>
  );
}

/** The proposal's pages and words beside the head's, read only once asked for. */
function Comparison(props: {
  place: Place;
  proposal: string;
  version: number;
  pages: { readonly head: number | null; readonly proposed: number | null };
  size: number | null;
}) {
  const [open, setOpen] = useState(false);
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

function Compared({
  place,
  proposal,
  version,
  pages,
}: {
  place: Place;
  proposal: string;
  version: number;
  pages: { readonly head: number | null; readonly proposed: number | null };
}) {
  const { context, tenant, workspace, artifact } = place;
  const { queries } = context;
  const [shown, setShown] = useState(PAGES_AT_ONCE);
  const most = Math.max(pages.head ?? 0, pages.proposed ?? 0);
  const numbers = Array.from({ length: Math.min(shown, most) }, (_, index) => index + 1);
  const has = (total: number | null, page: number) => total !== null && page <= total;
  const heads = useQueries({
    queries: numbers.map((page) => ({
      ...queries.files.page(tenant, workspace, artifact, version, page),
      enabled: has(pages.head, page),
    })),
  });
  const theirs = useQueries({
    queries: numbers.map((page) => ({
      ...queries.files.proposedPage(tenant, workspace, proposal, page),
      enabled: has(pages.proposed, page),
    })),
  });
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
  const shownOf = (
    read: Pick<UseQueryResult<string>, "data" | "isError"> | undefined,
    page: number,
  ): PageShown =>
    read?.data !== undefined
      ? { page, src: read.data }
      : { page, state: read?.isError ? "failed" : "reading" };
  const pairs = numbers.map(
    (page, index): PagePair => ({
      page,
      before: has(pages.head, page) ? shownOf(heads[index], page) : null,
      after: has(pages.proposed, page) ? shownOf(theirs[index], page) : null,
    }),
  );
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
      {pairs.length > 0 && (
        <PageCompare
          label="Its pages beside the head's"
          before={`Version ${version}`}
          after="Proposed"
          pages={pairs}
        />
      )}
      {numbers.length < most && (
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
