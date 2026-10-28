import { useMe } from "@portalr/client";
import {
  Ago,
  Button,
  Composer,
  ComposerDock,
  EmptyState,
  glyphs,
  Icon,
  IconButton,
  PageHeader,
  plainTitle,
  Row,
  RowLink,
  Rows,
  RunStatus,
  SegmentedFilter,
  Table,
  TextField,
} from "@portalr/ui";
import { createFileRoute, Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  type KeyboardEvent,
  useActionState,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { author } from "../../../../../../author";
import { alreadyMade, messageId } from "../../../../../../posting";
import { markSeen, readSeen, subscribeToSeen } from "../../../../../../seen";
import { Connection, useStream, useWorkspace } from "../../../../../../workspace";

type Shown = "all" | "needs" | "working";

/**
 * The workspace's threads, the most recently active first, as a table from 1024 pixels
 * and rows below it, and a new one, written to the agent in the composer docked at the page's
 * foot (portalr ADR-0087). The URL carries the filter (`show`), so a view is kept on reload and
 * can be shared; finding a thread by its title is the palette's.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/")({
  component: Threads,
  validateSearch: (search: Record<string, unknown>): { show?: Shown } =>
    search.show === "needs" || search.show === "working" ? { show: search.show } : {},
});

function Threads() {
  const { tenant, workspace } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const stream = useStream();
  const snapshot = useWorkspace();
  const navigate = useNavigate();
  const { show = "all" } = Route.useSearch();
  const view = (chosen: Shown) =>
    void navigate({
      to: ".",
      search: chosen === "all" ? {} : { show: chosen },
      replace: true,
    });
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
  // On a phone the composer waits behind the title row's New, as does a thread asked for from
  // the palette ("#new"): either opens it and takes the focus to its words (portalr ADR-0087).
  const [composing, setComposing] = useState(false);
  const compose = () => {
    setComposing(true);
    requestAnimationFrame(() =>
      document.querySelector<HTMLElement>("[data-composer-dock] textarea")?.focus(),
    );
  };
  const hash = useRouterState({ select: (state) => state.location.hash });
  const asked = useRef(compose);
  asked.current = compose;
  useEffect(() => {
    if (hash === "new") {
      asked.current();
    }
  }, [hash]);
  const live = snapshot.status === "live";
  // Each thread's run that is going, or waits on someone, said beside it.
  const going = new Map(
    Object.values(snapshot.state.runs)
      .filter((run) => run.status === "running" || run.status === "paused")
      .map((run) => [run.threadId, run.status] as const),
  );
  // Filtered by state (portalr ADR-0080); a thread this browser has read that has moved since is
  // marked. One never opened here is not: nothing is known of it.
  const seen = useSyncExternalStore(subscribeToSeen, () => readSeen(tenant, workspace));
  const all = Object.values(snapshot.state.threads).sort((a, b) => b.active - a.active);
  const needs = all.filter((thread) => going.get(thread.id) === "paused");
  const working = all.filter((thread) => going.get(thread.id) === "running");
  const listed = show === "needs" ? needs : show === "working" ? working : all;
  const rows = listed.map((thread) => {
    const last = thread.messages.at(-1);
    return {
      thread,
      title: thread.title || "Untitled",
      status: going.get(thread.id),
      // Who spoke last and what they said: what tells two threads of one title apart.
      said: last && `${author(last.actor, me)}: ${plainTitle(last.content) ?? "…"}`,
      when: thread.activeAt && <Ago at={thread.activeAt} />,
      moved: seen[thread.id] !== undefined && thread.active > (seen[thread.id] ?? 0),
      link: (
        <Link
          to="/t/$tenant/w/$workspace/threads/$thread"
          params={{ tenant, workspace, thread: thread.id }}
        />
      ),
    };
  });
  // Unread: a mark in the working colour in the row's own start padding, at the row's middle, so
  // the titles, and the lines under them, share one left edge (portalr ADR-0085).
  const unread = (
    <span
      role="img"
      aria-label="Moved since you read it"
      className="absolute start-2 top-1/2 size-2 -translate-y-1/2 rounded-full bg-accent forced-color-adjust-none forced-colors:bg-system-text"
    />
  );
  const filter = all.length > 0 && (
    <SegmentedFilter<Shown>
      label="Show"
      value={show}
      onValueChange={view}
      segments={[
        { value: "all", label: "All", count: all.length },
        { value: "needs", label: "Needs you", count: needs.length },
        { value: "working", label: "Working", count: working.length },
      ]}
    />
  );
  return (
    // A collection at most 1200 pixels wide, centred: rows wider than that only part the words
    // from their status (portalr ADR-0087).
    <div className="mx-auto flex w-full max-w-300 flex-1 flex-col gap-6 lg:gap-8">
      {/* The filter on the title's line, in its corner; on a phone, the row under it. */}
      <PageHeader
        title="Threads"
        actions={
          <>
            {filter && <div className="max-sm:hidden">{filter}</div>}
            {/* A phone's way to start one, at the title's end (portalr ADR-0087). */}
            <Button
              aria-label="New thread"
              title="New thread"
              className="hidden phone:flex"
              onClick={compose}
            >
              <Icon icon={glyphs.plus} />
              New
            </Button>
          </>
        }
      />
      {filter && <div className="sm:hidden">{filter}</div>}
      <Connection snapshot={snapshot} onReconnect={stream.reconnect} waiting="the workspace" />
      {live && all.length === 0 && (
        <EmptyState title="No threads yet">
          Write to the agent below to start one, or name one first.
        </EmptyState>
      )}
      {live && all.length > 0 && listed.length === 0 && (
        <EmptyState title="No thread here">None of the threads is in that state.</EmptyState>
      )}
      {rows.length > 0 && (
        // A table from 1024 pixels, its arrows moving from one thread's link to the
        // next's, and rows below it (portalr ADR-0087).
        <div className="contents">
          <div className="max-lg:hidden">
            <Table caption="Threads" className="table-fixed">
              <thead>
                <tr>
                  <th scope="col" className="w-[32%]">
                    Thread
                  </th>
                  <th scope="col">Last message</th>
                  <th scope="col" className="w-40">
                    Status
                  </th>
                  <th scope="col" data-num="" className="w-32">
                    Active
                  </th>
                  <th scope="col" className="w-10">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody onKeyDown={arrows}>
                {rows.map(({ thread, title, status, said, when, moved, link }) => (
                  <tr key={thread.id} className="group relative">
                    <th scope="row" className="truncate">
                      {moved && unread}
                      <RowLink render={link}>{title}</RowLink>
                    </th>
                    <td className="truncate text-muted">{said}</td>
                    <td>{status && <RunStatus status={status} />}</td>
                    <td data-num="" className="whitespace-nowrap text-muted">
                      {when}
                    </td>
                    <td>
                      {moved && (
                        <span className="block fine:opacity-0 fine:group-focus-within:opacity-100 fine:group-hover:opacity-100">
                          <IconButton
                            label="Mark as read"
                            icon={glyphs.check}
                            onClick={() => markSeen(tenant, workspace, thread.id, thread.active)}
                          />
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
          <div className="lg:hidden">
            <Rows label="Threads">
              {rows.map(({ thread, title, status, said, when, moved, link }) => (
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
                    <span className="block">
                      {moved && unread}
                      <RowLink
                        // Described by what was said last, not by a time that moves.
                        {...(said && { "aria-describedby": `${thread.id}-said` })}
                        render={link}
                      >
                        {title}
                      </RowLink>
                    </span>
                  }
                  end={status && <RunStatus status={status} />}
                />
              ))}
            </Rows>
          </div>
        </div>
      )}
      {/* At the page's foot, where a thread is written in (portalr ADR-0087): shown whatever the
          connection's state, so words kept through its closing stay in view, to send once it is
          connected again or to copy; disabled until it is live. On a phone it waits behind the
          title row's New (portalr ADR-0087), and the foot is the tab bar's. */}
      <ComposerDock className="mt-auto">
        <div
          // Being written, it holds the foot, and the tab bar gives way (portalr ADR-0087).
          data-composing={composing || undefined}
          className={composing ? "flex flex-col gap-3" : "flex flex-col gap-3 phone:hidden"}
        >
          <Composer
            disabled={!live}
            onSend={write}
            keep
            attach={
              // A quieter way in, inside the composer's row (portalr ADR-0085): name it, then
              // start it. It stays as the form opens, so the row keeps its shape.
              <Button
                variant="secondary"
                size="sm"
                disabled={!live}
                aria-expanded={naming}
                onClick={() => setNaming((was) => !was)}
              >
                <Icon icon={glyphs.plus} className="size-3.5" />
                Name it first…
              </Button>
            }
          />
          {naming && (
            <form className="flex flex-wrap items-end gap-2" action={start}>
              <TextField label="New thread" name="title" error={refused} required autoFocus />
              <Button type="submit" disabled={!live} pending={pending}>
                Start
              </Button>
            </form>
          )}
        </div>
      </ComposerDock>
    </div>
  );
}

/** From a thread's link, the arrows go to the next thread's or the one before's. */
function arrows(event: KeyboardEvent<HTMLElement>) {
  const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
  const from = event.target;
  if (step === undefined || !(from instanceof HTMLAnchorElement)) {
    return;
  }
  const links = [...(from.closest("tbody")?.querySelectorAll<HTMLAnchorElement>("th > a") ?? [])];
  const to = links[links.indexOf(from) + step];
  if (to) {
    event.preventDefault();
    to.focus();
  }
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
