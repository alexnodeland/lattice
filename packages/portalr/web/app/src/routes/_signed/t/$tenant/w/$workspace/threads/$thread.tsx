import { type Artifactr, type ArtifactrV1, thumbs } from "@portalr/client";
import {
  Composer,
  Message,
  Messages,
  ProposalCard,
  Request,
  RunStatus,
  Streaming,
  ToolCall,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/** A thread's chat: its messages, its runs as they go, its proposals, and a message to post. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/threads/$thread")({
  head: ({ params }) => ({ meta: [{ title: `Thread · ${params.workspace} · portalr` }] }),
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
  component: Chat,
});

/**
 * How to name who posted a message: the reader as "You", a person by their name, an agent as the
 * assistant, and an external agent, the system or an evaluator each as themselves.
 */
function author(actor: ArtifactrV1.Actor, me: string): string {
  switch (actor.kind) {
    case "user":
      return actor.id === me ? "You" : (actor.name ?? actor.id);
    case "agent":
      return "Assistant";
    case "external_agent":
      return actor.name ?? actor.client_id;
    case "system":
      return actor.name ?? "System";
    case "evaluator":
      return actor.name;
    default:
      return actor satisfies never;
  }
}

function Chat() {
  const { tenant, thread: id } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const memberships = useSuspenseQuery(queries.grantr.memberships(user)).data;
  // Who the server attributes this person's messages and feedback to, in this tenant.
  const me = memberships.find((membership) => membership.tenant === tenant)?.user ?? user;
  const stream = useStream();
  const snapshot = useWorkspace();
  const { threads, runs, proposals } = snapshot.state;
  const thread = threads[id];
  if (thread === undefined) {
    return snapshot.status === "live" ? (
      <section aria-labelledby="thread">
        <h2 id="thread" className="font-semibold text-lg">
          Thread not found
        </h2>
        <p>There's no thread here by that name, or it isn't one you can see.</p>
      </section>
    ) : (
      <Connection snapshot={snapshot} waiting="the thread" />
    );
  }
  const active = Object.values(runs).filter(
    (run) => run.threadId === id && (run.status === "running" || run.status === "paused"),
  );
  const proposed = Object.values(proposals).filter((proposal) => proposal.threadId === id);

  const give = (message: Artifactr.Message) => (up: boolean) =>
    stream.send({
      type: "give_feedback",
      feedback_type: "thumbs",
      target: { kind: "message", thread_id: id, message_id: message.id, run_id: message.runId },
      value: { up },
    });

  return (
    <section aria-labelledby="thread" className="flex flex-col gap-4">
      <h2 id="thread" className="font-semibold text-lg">
        {thread.title || "Untitled"}
      </h2>
      <Connection snapshot={snapshot} waiting="the thread" />
      <Messages>
        {thread.messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            author={author(message.actor, me)}
            thumbs={thumbs(message, me)}
            {...(message.runId !== null && { onThumbs: give(message) })}
          />
        ))}
        {active
          .filter((run) => run.text)
          .map((run) => (
            <Streaming key={run.id} text={run.text} author="Assistant" />
          ))}
      </Messages>
      {active.map((run) => (
        <div key={run.id} className="flex flex-col gap-2">
          <RunStatus status={run.status} />
          {Object.keys(run.tools).length > 0 && (
            <ul aria-label="Tools" className="flex flex-col gap-1">
              {Object.entries(run.tools).map(([call, tool]) => (
                <ToolCall key={call} tool={tool} />
              ))}
            </ul>
          )}
          {run.requests.map((request) => (
            <Request
              key={request.tool_call_id}
              request={request}
              onAnswer={(answer) =>
                stream.send({
                  type: "answer_deferred",
                  run_id: run.id,
                  tool_call_id: request.tool_call_id,
                  ...answer,
                })
              }
            />
          ))}
        </div>
      ))}
      {proposed.map((proposal) => (
        <ProposalCard
          key={proposal.id}
          proposal={proposal}
          onRespond={(decision) =>
            stream.send({ type: "respond_to_proposal", proposal_id: proposal.id, decision })
          }
        />
      ))}
      {snapshot.status !== "closed" && (
        <Composer
          disabled={snapshot.status !== "live"}
          onSend={(content) => stream.send({ type: "post_message", thread_id: id, content })}
        />
      )}
    </section>
  );
}
