import { type Artifactr, type ArtifactrV1, keys, thumbs } from "@portalr/client";
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
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { allowedIn } from "../../../../../../../allowed";
import { useMe } from "../../../../../../../me";
import { ShareDialog } from "../../../../../../../share-dialog";
import { ThreadMenu } from "../../../../../../../thread-menu";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/** What a person may do with a thread, asked of grantr on the thread itself. */
const ACTIONS = [
  "artifactr:post_message",
  "grantr:grant",
  "grantr:revoke",
  "grantr:restrict",
] as const;

/** Who may list the tenant's members, to share with any of them. */
const LISTS_MEMBERS = ["grantr:add_member"] as const;

const threadOf = (workspace: string, thread: string) =>
  ({ kind: "thread", workspace, id: thread }) as const;

/**
 * A thread's chat: its messages, its runs as they go, its proposals, and a message to post where
 * grantr allows; and its menu, to restrict and share it, for those who may (portalr ADR-0022).
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/threads/$thread")({
  head: ({ params }) => ({ meta: [{ title: `Thread · ${params.workspace} · portalr` }] }),
  loader: async ({ context, params }) => {
    const { tenant, workspace, thread } = params;
    const { queries, queryClient } = context;
    const [, answers] = await Promise.all([
      queryClient.ensureQueryData(queries.grantr.memberships(context.user)),
      queryClient.ensureQueryData(
        allowedIn(queries, tenant, workspace, ACTIONS, threadOf(workspace, thread)),
      ),
      queryClient.ensureQueryData(
        allowedIn(queries, tenant, workspace, LISTS_MEMBERS, { kind: "tenant" }),
      ),
    ]);
    const may = (action: (typeof ACTIONS)[number]) => answers[ACTIONS.indexOf(action)] === true;
    await Promise.all([
      may("grantr:grant") && queryClient.ensureQueryData(queries.grantr.grants(tenant, workspace)),
      may("grantr:restrict") &&
        queryClient.ensureQueryData(queries.grantr.restrictions(tenant, workspace)),
    ]);
  },
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
  const { tenant, workspace, thread: id } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspace, ACTIONS, threadOf(workspace, id)),
    [queries, tenant, workspace, id],
  );
  const { data: allowed } = useSuspenseQuery(checks);
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

  const give = (message: Artifactr.Message) => (up: boolean, comment: string | null) =>
    stream.send({
      type: "give_feedback",
      feedback_type: "thumbs",
      target: { kind: "message", thread_id: id, message_id: message.id, run_id: message.runId },
      value: comment === null ? { up } : { up, comment },
    });

  return (
    <section aria-labelledby="thread" className="flex flex-col gap-4">
      <span className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="thread" className="font-semibold text-lg">
          {thread.title || "Untitled"}
        </h2>
        <Access tenant={tenant} workspace={workspace} thread={id} allowed={allowed} />
      </span>
      <Connection snapshot={snapshot} waiting="the thread" />
      <Messages>
        {thread.messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            author={author(message.actor, me)}
            thumbs={thumbs(message.feedback, me)}
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
      {snapshot.status !== "closed" && allowed.has("artifactr:post_message") && (
        <Composer
          disabled={snapshot.status !== "live"}
          onSend={(content) => stream.send({ type: "post_message", thread_id: id, content })}
        />
      )}
    </section>
  );
}

/**
 * The thread's menu and its sharing, for whoever grantr lets grant, revoke or restrict on it: the
 * grants on it, and whether it's restricted, as grantr holds them.
 */
function Access({
  tenant,
  workspace,
  thread,
  allowed,
}: {
  tenant: string;
  workspace: string;
  thread: string;
  allowed: ReadonlySet<string>;
}) {
  const { queries, commands, queryClient } = Route.useRouteContext();
  const [sharing, setSharing] = useState(false);
  const canShare = allowed.has("grantr:grant");
  const canRestrict = allowed.has("grantr:restrict");
  const lister = useMemo(
    () => allowedIn(queries, tenant, workspace, LISTS_MEMBERS, { kind: "tenant" }),
    [queries, tenant, workspace],
  );
  const { data: lists } = useSuspenseQuery(lister);
  const grants = useQuery({ ...queries.grantr.grants(tenant, workspace), enabled: canShare });
  const restrictions = useQuery({
    ...queries.grantr.restrictions(tenant, workspace),
    enabled: canRestrict,
  });
  const members = useQuery({
    ...queries.grantr.members(tenant),
    enabled: canShare && lists.has("grantr:add_member"),
  });
  const on = threadOf(workspace, thread);
  const held = (grants.data ?? []).filter(
    (grant) => grant.on.kind === "thread" && grant.on.id === thread,
  );
  const restricted = (restrictions.data ?? []).some(
    (item) => item.kind === "thread" && item.id === thread,
  );
  // The people it may be shared with: those with a role in the workspace, and, for whoever may
  // list them, the tenant's members; less those who hold a role on it already.
  const holding = new Set(held.flatMap((grant) => (grant.to.kind === "user" ? [grant.to.id] : [])));
  const people = [
    ...new Set([
      ...(grants.data ?? []).flatMap((grant) =>
        grant.on.kind === "workspace" && grant.to.kind === "user" ? [grant.to.id] : [],
      ),
      ...(members.data ?? []).flatMap((member) => (member.kind === "user" ? [member.id] : [])),
    ]),
  ]
    .filter((person) => !holding.has(person))
    .sort();
  /** A change to access, after which grantr's answers are read again. */
  async function changed<A extends { outcome: string }>(answer: Promise<A>): Promise<A> {
    const answered = await answer;
    if (answered.outcome === "done") {
      await queryClient.invalidateQueries({ queryKey: keys.grantr.access(tenant) });
    }
    return answered;
  }
  return (
    <>
      {restricted && (
        <p className="text-muted text-sm">Restricted to the people it's shared with</p>
      )}
      <ThreadMenu
        restricted={restricted}
        canRestrict={canRestrict}
        canShare={canShare}
        onRestrict={() =>
          changed(commands.grantr.restrict(tenant, { on, restricted: !restricted }))
        }
        onShare={() => setSharing(true)}
      />
      {canShare && (
        <ShareDialog
          open={sharing}
          onOpenChange={setSharing}
          grants={held}
          people={people}
          canRevoke={allowed.has("grantr:revoke")}
          onGrant={(person, role) =>
            changed(commands.grantr.grant(tenant, { role, on, to: { kind: "user", id: person } }))
          }
          onRevoke={(grant) =>
            changed(commands.grantr.revoke(tenant, { role: grant.role, on, to: grant.to }))
          }
        />
      )}
    </>
  );
}
