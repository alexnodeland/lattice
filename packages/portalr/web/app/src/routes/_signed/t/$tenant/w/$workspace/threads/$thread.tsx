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
import { useStream, useWorkspace } from "../../../../../../../workspace";

/** A thread's chat: its messages, its runs as they go, its proposals, and a message to post. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/threads/$thread")({
  component: Chat,
});

/** How to name who posted a message: a person by their id, an agent as the assistant. */
function author(actor: ArtifactrV1.Actor): string {
  return actor.kind === "user" && "id" in actor ? actor.id : "Assistant";
}

function Chat() {
  const { tenant, thread: id } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const memberships = useSuspenseQuery(queries.grantr.memberships(user)).data;
  // Who the server attributes this person's messages and feedback to, in this tenant.
  const me = memberships.find((membership) => membership.tenant === tenant)?.user ?? user;
  const stream = useStream();
  const { threads, runs, proposals } = useWorkspace();
  const thread = threads[id];
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
        {thread?.title || id}
      </h2>
      <Messages>
        {(thread?.messages ?? []).map((message) => (
          <Message
            key={message.id}
            message={message}
            author={author(message.actor)}
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
          <ul aria-label="Tools" className="flex flex-col gap-1">
            {Object.entries(run.tools).map(([call, tool]) => (
              <ToolCall key={call} tool={tool} />
            ))}
          </ul>
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
      <Composer
        onSend={(content) => stream.send({ type: "post_message", thread_id: id, content })}
      />
    </section>
  );
}
