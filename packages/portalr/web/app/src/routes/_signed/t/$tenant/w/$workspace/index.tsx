import { useMe } from "@portalr/client";
import {
  Ago,
  Button,
  Composer,
  EmptyState,
  PageHeader,
  plainTitle,
  Row,
  RowLink,
  Rows,
  RunStatus,
  TextField,
} from "@portalr/ui";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useActionState, useState } from "react";
import { author } from "../../../../../../author";
import { Connection, useStream, useWorkspace } from "../../../../../../workspace";

/** The workspace's threads, the most recently active first, and a new one. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/")({ component: Threads });

function Threads() {
  const { tenant, workspace } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const stream = useStream();
  const snapshot = useWorkspace();
  const navigate = useNavigate();
  const listed = Object.values(snapshot.state.threads).sort((a, b) => b.active - a.active);
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
  // first message what was written. Refused, the words stay in the composer.
  const write = async (content: string) => {
    const thread = newThreadId();
    const created = await stream.send({
      type: "create_thread",
      thread_id: thread,
      title: firstLine(content),
    });
    if (created.outcome !== "done") {
      return created;
    }
    const posted = await stream.send({
      type: "post_message",
      thread_id: thread,
      message_id: `msg_${crypto.randomUUID().replaceAll("-", "")}`,
      content,
    });
    // The thread is there either way: the page moves to it, where the message is sent again if need be.
    await toThread(thread);
    return posted;
  };
  const [naming, setNaming] = useState(false);
  const live = snapshot.status === "live";
  // Each thread's run that is going, or waits on someone, said beside it.
  const going = new Map(
    Object.values(snapshot.state.runs)
      .filter((run) => run.status === "running" || run.status === "paused")
      .map((run) => [run.threadId, run.status] as const),
  );
  const starting =
    snapshot.status !== "closed" ? (
      <div className="flex flex-col gap-2">
        <Composer disabled={!live} onSend={write} />
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
    ) : null;
  return (
    <>
      <PageHeader
        title="Threads"
        meta={`The threads in ${workspace}, the most recently active first`}
      />
      {starting}
      <Connection snapshot={snapshot} waiting="the workspace" />
      {live && listed.length === 0 && (
        <EmptyState title="No threads yet">
          Write to the agent above to start one, or name one first.
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
