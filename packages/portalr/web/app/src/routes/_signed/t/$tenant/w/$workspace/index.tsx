import {
  Button,
  EmptyState,
  PageHeader,
  Row,
  RowLink,
  Rows,
  RunStatus,
  TextField,
} from "@portalr/ui";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useActionState } from "react";
import { Connection, useStream, useWorkspace } from "../../../../../../workspace";

/** The workspace's threads, the most recently active first, and a new one. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/")({ component: Threads });

function Threads() {
  const { tenant, workspace } = Route.useParams();
  const stream = useStream();
  const snapshot = useWorkspace();
  const navigate = useNavigate();
  const listed = Object.values(snapshot.state.threads).sort((a, b) => b.active - a.active);
  const [refused, start, pending] = useActionState(
    async (_last: string | null, form: FormData): Promise<string | null> => {
      const thread = `thr_${crypto.randomUUID().replaceAll("-", "")}`;
      const title = String(form.get("title"));
      const settled = await stream.send({ type: "create_thread", thread_id: thread, title });
      if (settled.outcome !== "done") {
        return settled.outcome === "refused"
          ? "The thread wasn't started: the server refused it."
          : "The thread wasn't started: the connection closed.";
      }
      await navigate({
        to: "/t/$tenant/w/$workspace/threads/$thread",
        params: { tenant, workspace, thread },
      });
      return null;
    },
    null,
  );
  const live = snapshot.status === "live";
  // Each thread's run that is going, or waits on someone, said beside it.
  const going = new Map(
    Object.values(snapshot.state.runs)
      .filter((run) => run.status === "running" || run.status === "paused")
      .map((run) => [run.threadId, run.status] as const),
  );
  const starting =
    snapshot.status !== "closed" ? (
      <form className="flex items-end gap-2" action={start}>
        <TextField label="New thread" name="title" error={refused} required />
        <Button type="submit" disabled={pending || !live}>
          Start
        </Button>
      </form>
    ) : null;
  return (
    <>
      <PageHeader
        title="Threads"
        meta={`The threads in ${workspace}, the most recently active first`}
        actions={starting}
      />
      <Connection snapshot={snapshot} waiting="the workspace" />
      {live && listed.length === 0 && (
        <EmptyState title="No threads yet">
          Name one in New thread, and talk with the agent in it.
        </EmptyState>
      )}
      {listed.length > 0 && (
        <Rows label="Threads">
          {listed.map((thread) => {
            const status = going.get(thread.id);
            return (
              <Row
                key={thread.id}
                name={
                  <RowLink
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
