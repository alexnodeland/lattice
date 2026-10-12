import { Button, TextField, TextLink } from "@portalr/ui";
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
  return (
    <section aria-labelledby="threads" className="flex flex-col gap-4">
      <h2 id="threads" className="font-semibold text-lg">
        Threads
      </h2>
      <Connection snapshot={snapshot} waiting="the workspace" />
      {live && listed.length === 0 && <p>No threads yet.</p>}
      {listed.length > 0 && (
        <ul aria-label="Threads" className="flex flex-col gap-2">
          {listed.map((thread) => (
            <li key={thread.id}>
              <TextLink
                render={
                  <Link
                    to="/t/$tenant/w/$workspace/threads/$thread"
                    params={{ tenant, workspace, thread: thread.id }}
                  />
                }
              >
                {thread.title || "Untitled"}
              </TextLink>
            </li>
          ))}
        </ul>
      )}
      {snapshot.status !== "closed" && (
        <form className="flex max-w-sm flex-col gap-2" action={start}>
          <TextField label="New thread" name="title" error={refused} required />
          <Button type="submit" disabled={pending || !live}>
            Start
          </Button>
        </form>
      )}
    </section>
  );
}
