import { useMe } from "@portalr/client";
import {
  Ago,
  ASK_FORM,
  ASK_USER,
  Button,
  Composer,
  EmptyState,
  PageHeader,
  plainTitle,
  Row,
  RowLink,
  Rows,
  RunStatus,
  SectionTitle,
  SegmentedFilter,
  StatusBadge,
  TextField,
} from "@portalr/ui";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useActionState, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { author } from "../../../../../../author";
import { alreadyMade, messageId } from "../../../../../../posting";
import { readSeen, subscribeToSeen } from "../../../../../../seen";
import { Connection, useStream, useWorkspace } from "../../../../../../workspace";

type Shown = "all" | "needs" | "working";

/**
 * The workspace's threads, the most recently active first, and a new one. The URL carries the
 * search (`q`) and the filter (`show`), so a view is kept on reload and can be shared.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/")({
  component: Threads,
  validateSearch: (search: Record<string, unknown>): { q?: string; show?: Shown } => ({
    ...(typeof search.q === "string" && search.q !== "" && { q: search.q }),
    ...((search.show === "needs" || search.show === "working") && { show: search.show }),
  }),
});

function Threads() {
  const { tenant, workspace } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const stream = useStream();
  const snapshot = useWorkspace();
  const navigate = useNavigate();
  const { q = "", show = "all" } = Route.useSearch();
  // What is typed is the page's own at once; the URL follows after a pause, trimmed, so each
  // keystroke isn't a navigation; a URL that changes under it, as Back does, is taken up.
  const [typed, setTyped] = useState(q);
  useEffect(() => {
    setTyped((now) => (now.trim() === q ? now : q));
  }, [q]);
  const view = (change: { q?: string; show?: Shown }) =>
    void navigate({
      to: ".",
      search: (was) => {
        const next = { ...was, ...change };
        return {
          ...(next.q && { q: next.q }),
          ...(next.show && next.show !== "all" && { show: next.show }),
        };
      },
      replace: true,
    });
  const viewNow = useRef(view);
  viewNow.current = view;
  useEffect(() => {
    const want = typed.trim();
    if (want === q) {
      return;
    }
    const timer = setTimeout(() => viewNow.current({ q: want }), 200);
    return () => clearTimeout(timer);
  }, [typed, q]);
  const toThread = (thread: string) =>
    navigate({
      to: "/t/$tenant/w/$workspace/threads/$thread",
      params: { tenant, workspace, thread },
    });
  const [refused, start, pending] = useActionState(
    async (_last: string | null, form: FormData): Promise<string | null> => {
      const thread = newThreadId();
      const title = String(form.get("title"));
      const settled = await stream.send({ type: "create_thread", thread_id: thread, title });
      if (settled.outcome !== "done") {
        return settled.outcome === "refused"
          ? "The thread wasn't started: the server refused it."
          : "The thread wasn't started: the connection closed.";
      }
      await toThread(thread);
      return null;
    },
    null,
  );
  // A thread started by writing to the agent (portalr ADR-0080): its title is the first line, its
  // first message what was written. The ids are fixed per draft, so the words, kept in the
  // composer on any failure, sent again make nothing twice: a thread already made is gone on
  // from, a message already posted is done. The page moves to the thread on success alone.
  const attempt = useRef<{ content: string; thread: string; message: string } | null>(null);
  const write = async (content: string) => {
    const ids =
      attempt.current?.content === content
        ? attempt.current
        : { content, thread: newThreadId(), message: messageId() };
    attempt.current = ids;
    const created = await stream.send({
      type: "create_thread",
      thread_id: ids.thread,
      title: firstLine(content),
    });
    if (created.outcome !== "done" && !alreadyMade(created, "thread", ids.thread)) {
      return created;
    }
    const posted = await stream.send({
      type: "post_message",
      thread_id: ids.thread,
      message_id: ids.message,
      content,
    });
    if (posted.outcome !== "done" && !alreadyMade(posted, "message", ids.message)) {
      return posted;
    }
    attempt.current = null;
    await toThread(ids.thread);
    return { outcome: "done" as const };
  };
  const [naming, setNaming] = useState(false);
  const live = snapshot.status === "live";
  // What waits on a person across the workspace's threads (portalr ADR-0080): calls to approve
  // first, the riskier before the rest, then questions; each opens its thread at the request.
  const needed = Object.values(snapshot.state.runs)
    .filter((run) => run.status === "paused")
    .flatMap((run) => run.requests.map((request) => ({ request, thread: run.threadId })))
    // A thread the stream hasn't shown the reader is one they can't see: no way to a not-found.
    .filter(({ thread }) => snapshot.state.threads[thread] !== undefined)
    .map(({ request, thread }) => {
      const question = request.tool_name === ASK_USER || request.tool_name === ASK_FORM;
      const risk = request.review?.risk;
      const rank = question ? 3 : risk === "network" ? 0 : risk === undefined ? 2 : 1;
      const title = snapshot.state.threads[thread]?.title || "Untitled";
      return { request, thread, title, rank, question, risk };
    })
    .sort((a, b) => a.rank - b.rank);
  // Each thread's run that is going, or waits on someone, said beside it.
  const going = new Map(
    Object.values(snapshot.state.runs)
      .filter((run) => run.status === "running" || run.status === "paused")
      .map((run) => [run.threadId, run.status] as const),
  );
  // Searched by title and filtered by state (portalr ADR-0080); a thread this browser has read
  // that has moved since is marked. One never opened here is not: nothing is known of it.
  const seen = useSyncExternalStore(subscribeToSeen, () => readSeen(tenant, workspace));
  const all = Object.values(snapshot.state.threads).sort((a, b) => b.active - a.active);
  const needs = all.filter((thread) => going.get(thread.id) === "paused");
  const working = all.filter((thread) => going.get(thread.id) === "running");
  const shown = show === "needs" ? needs : show === "working" ? working : all;
  const words = q.trim().toLocaleLowerCase();
  const listed = words
    ? shown.filter((thread) => (thread.title || "Untitled").toLocaleLowerCase().includes(words))
    : shown;
  const finding = all.length > 0 && (
    <div className="flex flex-wrap items-end gap-3">
      <TextField
        type="search"
        label="Search threads"
        value={typed}
        onChange={(event) => setTyped(event.currentTarget.value)}
        autoComplete="off"
        enterKeyHint="search"
        className="min-w-48 flex-1"
      />
      <SegmentedFilter<Shown>
        label="Show"
        value={show}
        onValueChange={(chosen) => view({ show: chosen })}
        segments={[
          { value: "all", label: "All", count: all.length },
          { value: "needs", label: "Needs you", count: needs.length },
          { value: "working", label: "Working", count: working.length },
        ]}
      />
    </div>
  );
  // Shown whatever the connection's state, so words kept through its closing stay in view, to
  // send once it is connected again or to copy; disabled until it is live.
  const starting = (
    <div className="flex flex-col gap-2">
      <Composer disabled={!live} onSend={write} keep />
      <div className="flex flex-wrap items-end gap-2">
        {naming ? (
          <form className="flex flex-wrap items-end gap-2" action={start}>
            <TextField label="New thread" name="title" error={refused} required autoFocus />
            <Button type="submit" disabled={!live} pending={pending}>
              Start
            </Button>
          </form>
        ) : (
          <Button variant="ghost" size="sm" disabled={!live} onClick={() => setNaming(true)}>
            Name it first…
          </Button>
        )}
      </div>
    </div>
  );
  return (
    <>
      <PageHeader
        title="Threads"
        meta={`The threads in ${workspace}, the most recently active first`}
      />
      {starting}
      <Connection snapshot={snapshot} onReconnect={stream.reconnect} waiting="the workspace" />
      {needed.length > 0 && (
        <section aria-labelledby="needs-you" className="flex flex-col gap-3">
          <SectionTitle id="needs-you">
            Needs you{" "}
            <span className="font-mono font-normal text-muted text-sm tabular-nums">
              {needed.length}
            </span>
          </SectionTitle>
          <Rows label="Needs you">
            {needed.map(({ request, thread, title, question, risk }) => (
              <Row
                key={request.tool_call_id}
                name={
                  <RowLink
                    render={
                      <Link
                        to="/t/$tenant/w/$workspace/threads/$thread"
                        params={{ tenant, workspace, thread }}
                        hash={`request-${request.tool_call_id}`}
                      />
                    }
                  >
                    {question ? "A question" : `Approve ${request.tool_name}`}
                  </RowLink>
                }
                meta={`in ${title}`}
                end={
                  risk !== undefined && (
                    <StatusBadge tone="retrying">
                      {risk === "network" ? "Downloads from the internet" : "Runs code"}
                    </StatusBadge>
                  )
                }
              />
            ))}
          </Rows>
        </section>
      )}
      {finding}
      {live && all.length === 0 && (
        <EmptyState title="No threads yet">
          Write to the agent above to start one, or name one first.
        </EmptyState>
      )}
      {live && all.length > 0 && listed.length === 0 && (
        <EmptyState title="No thread matches">
          None of the threads is {show === "all" ? "named so" : "in that state and named so"}.
        </EmptyState>
      )}
      {listed.length > 0 && (
        <Rows label="Threads">
          {listed.map((thread) => {
            const status = going.get(thread.id);
            const last = thread.messages.at(-1);
            // Who spoke last and what they said, and when: what tells two threads of one title apart.
            const said = last && `${author(last.actor, me)}: ${plainTitle(last.content) ?? "…"}`;
            const when = thread.activeAt && <Ago at={thread.activeAt} />;
            return (
              <Row
                key={thread.id}
                meta={
                  (said || when) && (
                    <>
                      {said && <span id={`${thread.id}-said`}>{said}</span>}
                      {said && when && " · "}
                      {when}
                    </>
                  )
                }
                name={
                  <span className="flex items-center gap-2">
                    {/* Unread: a mark in the working colour at the row's start (portalr ADR-0081). */}
                    {seen[thread.id] !== undefined && thread.active > (seen[thread.id] ?? 0) && (
                      <span
                        role="img"
                        aria-label="Moved since you read it"
                        className="size-2 shrink-0 rounded-full bg-accent"
                      />
                    )}
                    <RowLink
                      // Described by what was said last, not by a time that moves.
                      {...(said && { "aria-describedby": `${thread.id}-said` })}
                      render={
                        <Link
                          to="/t/$tenant/w/$workspace/threads/$thread"
                          params={{ tenant, workspace, thread: thread.id }}
                        />
                      }
                    >
                      {thread.title || "Untitled"}
                    </RowLink>
                  </span>
                }
                end={status && <RunStatus status={status} />}
              />
            );
          })}
        </Rows>
      )}
    </>
  );
}

const newThreadId = () => `thr_${crypto.randomUUID().replaceAll("-", "")}`;

/** A thread's title from what starts it: the first line, cut where a title would be too long. */
const firstLine = (content: string) => {
  const line =
    content
      .split("\n")
      .find((each) => each.trim() !== "")
      ?.trim() ?? "";
  return line.length > 80 ? `${line.slice(0, 79).trimEnd()}…` : line;
};
