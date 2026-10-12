import { Button, TextField, TextLink } from "@portalr/ui";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useActionState } from "react";
import { useStream, useWorkspace } from "../../../../../../workspace";

/** The workspace's threads, and a new one. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/")({ component: Threads });

function Threads() {
  const { tenant, workspace } = Route.useParams();
  const stream = useStream();
  const { threads } = useWorkspace();
  const navigate = useNavigate();
  const listed = Object.values(threads).sort((a, b) => a.title.localeCompare(b.title));
  const [refused, start, pending] = useActionState(
    async (_last: string | null, form: FormData): Promise<string | null> => {
      const thread = `thr_${crypto.randomUUID().replaceAll("-", "")}`;
      const title = String(form.get("title"));
      const settled = await stream.send({ type: "create_thread", thread_id: thread, title });
      if (settled.outcome !== "done") {
        return "The thread wasn't started. Try again.";
      }
      await navigate({
        to: "/t/$tenant/w/$workspace/threads/$thread",
        params: { tenant, workspace, thread },
      });
      return null;
    },
    null,
  );
  return (
    <section aria-labelledby="threads" className="flex flex-col gap-4">
      <h2 id="threads" className="font-semibold text-lg">
        Threads
      </h2>
      {listed.length === 0 ? (
        <p>No threads yet.</p>
      ) : (
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
                {thread.title || thread.id}
              </TextLink>
            </li>
          ))}
        </ul>
      )}
      <form className="flex max-w-sm flex-col gap-2" action={start}>
        <TextField label="New thread" name="title" error={refused} required />
        <Button type="submit" disabled={pending}>
          Start
        </Button>
      </form>
    </section>
  );
}
