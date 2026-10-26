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
  StatusBadge,
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
  // What waits on a person across the workspace's threads (portalr ADR-0080): calls to approve
  // first, the riskier before the rest, then questions; each opens its thread at the request.
  const needed = Object.values(snapshot.state.runs)
    .filter((run) => run.status === "paused")
    .flatMap((run) => run.requests.map((request) => ({ request, thread: run.threadId })))
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
      {needed.length > 0 && (
        <section aria-labelledby="needs-you" className="flex flex-col gap-3">
          <SectionTitle id="needs-you">Needs you</SectionTitle>
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
