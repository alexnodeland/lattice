import {
  type Artifactr,
  type ArtifactrV1,
  allowedIn,
  changedAccess,
  type GrantrApi,
  thumbs,
  useMe,
  workspaceOf,
} from "@portalr/client";
import {
  Composer,
  Message,
  Messages,
  PageHeader,
  ProposalCard,
  Request,
  RunStatus,
  Streaming,
  TextLink,
  ToolCall,
} from "@portalr/ui";
import {
  type UseSuspenseQueryOptions,
  useSuspenseQueries,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { CatchBoundary, createFileRoute, Link } from "@tanstack/react-router";
import { type ReactNode, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ShareDialog } from "../../../../../../../share-dialog";
import { ThreadMenu } from "../../../../../../../thread-menu";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/**
 * What a person may do with a thread, asked of grantr on the thread itself: reading it, which a
 * restriction takes away while it's open, posting in it, and changing who sees it.
 */
const ACTIONS = [
  "artifactr:read_threads",
  "artifactr:post_message",
  "grantr:grant",
  "grantr:revoke",
  "grantr:restrict",
] as const;

/** Listing a workspace's grants, and its restrictions, is asked on the workspace. */
const LISTS = ["grantr:grant", "grantr:restrict"] as const;

/** Listing the tenant's members, to share with any of them, is asked on the tenant. */
const MEMBERS = ["grantr:add_member"] as const;

const threadOf = (workspace: string, thread: string) =>
  ({ kind: "thread", workspace, id: thread }) as const;

const TENANT = { kind: "tenant" } as const;

/**
 * A thread's chat: its messages, its runs as they go, its proposals, and a message to post where
 * grantr allows; and its menu, to restrict and share it, for those who may (portalr ADR-0022).
 * What grantr allows is asked again on focus, on a reconnect, and when a post is refused, so a
 * thread restricted while it's open says so.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/threads/$thread")({
  head: ({ params }) => ({ meta: [{ title: `Thread · ${params.workspace} · portalr` }] }),
  loader: async ({ context, params }) => {
    const { tenant, workspace, thread } = params;
    const { queries, queryClient } = context;
    const checks = allowedIn(queries, tenant, threadOf(workspace, thread), ACTIONS);
    const allowed = checks.select(await queryClient.ensureQueryData(checks));
    if (allowed.has("grantr:grant") || allowed.has("grantr:restrict")) {
      await prefetchAccess(context, tenant, workspace);
    }
  },
  component: Chat,
});

type Context = ReturnType<typeof Route.useRouteContext>;

/** What the access subtree reads, read ahead, as far as grantr allows; it never throws. */
async function prefetchAccess({ queries, queryClient }: Context, tenant: string, ws: string) {
  const lists = allowedIn(queries, tenant, workspaceOf(ws), LISTS);
  const members = allowedIn(queries, tenant, TENANT, MEMBERS);
  const [inWorkspace, inTenant] = await Promise.all([
    queryClient.ensureQueryData(lists).then(lists.select),
    queryClient.ensureQueryData(members).then(members.select),
  ]).catch(() => [new Set<string>(), new Set<string>()]);
  await Promise.all(
    readsFor(queries, tenant, ws, inWorkspace, inTenant).map(
      (read) => read && queryClient.prefetchQuery(read),
    ),
  );
}

/** The access reads grantr allows: the workspace's grants and restrictions, and the members. */
function readsFor(
  queries: Context["queries"],
  tenant: string,
  ws: string,
  inWorkspace: ReadonlySet<string>,
  inTenant: ReadonlySet<string>,
) {
  return [
    inWorkspace.has("grantr:grant") ? queries.grantr.grants(tenant, ws) : null,
    inWorkspace.has("grantr:restrict") ? queries.grantr.restrictions(tenant, ws) : null,
    inTenant.has("grantr:add_member") ? queries.grantr.members(tenant) : null,
  ] as const;
}

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
  const crumb = (
    <TextLink render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}>
      Threads
    </TextLink>
  );
  const { queries, queryClient, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const checks = useMemo(
    () => allowedIn(queries, tenant, threadOf(workspace, id), ACTIONS),
    [queries, tenant, workspace, id],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  const stream = useStream();
  const snapshot = useWorkspace();
  // Ask grantr again on a reconnect: access may have changed while the connection was down.
  const wasLive = useRef(false);
  useEffect(() => {
    if (snapshot.status === "live") {
      if (wasLive.current) {
        void queryClient.invalidateQueries({ queryKey: checks.queryKey });
      }
      wasLive.current = true;
    }
  }, [snapshot.status, queryClient, checks.queryKey]);
  const { threads, runs, proposals } = snapshot.state;
  const thread = threads[id];
  if (thread === undefined) {
    return snapshot.status === "live" ? (
      <>
        <PageHeader title="Thread not found" crumb={crumb} />
        <p>There's no thread here by that name, or it isn't one you can see.</p>
      </>
    ) : (
      <Connection snapshot={snapshot} waiting="the thread" />
    );
  }
  if (!allowed.has("artifactr:read_threads")) {
    return (
      <>
        <PageHeader title={thread.title || "Untitled"} crumb={crumb} />
        <p role="alert">This isn't available to you any more.</p>
      </>
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
    <section aria-labelledby="thread" className="flex max-w-190 flex-col gap-6">
      <PageHeader
        title={thread.title || "Untitled"}
        crumb={crumb}
        id="thread"
        actions={
          (allowed.has("grantr:grant") || allowed.has("grantr:restrict")) && (
            <CatchBoundary
              getResetKey={() => id}
              errorComponent={() => <p role="alert">Who has access to it couldn't be read.</p>}
            >
              <Suspense fallback={null}>
                <Access tenant={tenant} workspace={workspace} thread={id} allowed={allowed} />
              </Suspense>
            </CatchBoundary>
          )
        }
      />
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
        <div className="sticky bottom-0 z-10 bg-paper pt-2 pb-4">
          <Composer
            disabled={snapshot.status !== "live"}
            onSend={async (content) => {
              const sent = await stream.send({ type: "post_message", thread_id: id, content });
              if (sent.outcome === "refused") {
                // Refused, perhaps since they may no longer post or read it: ask grantr again.
                void queryClient.invalidateQueries({ queryKey: checks.queryKey });
              }
              return sent;
            }}
          />
        </div>
      )}
    </section>
  );
}

/** A read where grantr allows it, or null without a request where it doesn't. */
function Read<T>({
  options,
  children,
}: {
  options: UseSuspenseQueryOptions<T, Error, T, readonly unknown[]> | null;
  children: (data: T | null) => ReactNode;
}) {
  return options === null ? children(null) : <Reading options={options}>{children}</Reading>;
}

function Reading<T>({
  options,
  children,
}: {
  options: UseSuspenseQueryOptions<T, Error, T, readonly unknown[]>;
  children: (data: T) => ReactNode;
}) {
  return children(useSuspenseQuery(options).data);
}

/**
 * The thread's menu and its sharing, for whoever grantr lets grant or restrict on it. Its lists
 * are read where grantr allows them: the workspace's grants and restrictions on the workspace,
 * and the tenant's members on the tenant.
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
  const { queries } = Route.useRouteContext();
  const [inWorkspace, inTenant] = useSuspenseQueries({
    queries: [
      allowedIn(queries, tenant, workspaceOf(workspace), LISTS),
      allowedIn(queries, tenant, TENANT, MEMBERS),
    ],
  }).map((answer) => answer.data);
  const [grants, restrictions, members] = readsFor(
    queries,
    tenant,
    workspace,
    inWorkspace ?? new Set(),
    inTenant ?? new Set(),
  );
  return (
    <Read<Grant[]> options={grants}>
      {(granted) => (
        <Read<Resource[]> options={restrictions}>
          {(restricted) => (
            <Read<Member[]> options={members}>
              {(listed) => (
                <Sharing
                  tenant={tenant}
                  workspace={workspace}
                  thread={thread}
                  allowed={allowed}
                  granted={granted}
                  restricted={restricted}
                  members={listed}
                />
              )}
            </Read>
          )}
        </Read>
      )}
    </Read>
  );
}

type Grant = GrantrApi.components["schemas"]["Grant"];
type Resource = GrantrApi.components["schemas"]["Resource"];
type Member = GrantrApi.components["schemas"]["Member"];

/** The menu, the restriction it shows, and the sharing dialog, over what was read. */
function Sharing({
  tenant,
  workspace,
  thread,
  allowed,
  granted,
  restricted,
  members,
}: {
  tenant: string;
  workspace: string;
  thread: string;
  allowed: ReadonlySet<string>;
  granted: readonly Grant[] | null;
  restricted: readonly Resource[] | null;
  members: readonly Member[] | null;
}) {
  const { commands, queryClient } = Route.useRouteContext();
  const [sharing, setSharing] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const on = threadOf(workspace, thread);
  const held =
    granted?.filter((grant) => grant.on.kind === "thread" && grant.on.id === thread) ?? null;
  const isRestricted =
    allowed.has("grantr:restrict") && restricted !== null
      ? restricted.some((item) => item.kind === "thread" && item.id === thread)
      : null;
  // The people it may be shared with: those with a role in the workspace, and, for whoever may
  // list them, the tenant's members; less those who hold a role on it already.
  const holding = new Set(
    (held ?? []).flatMap((grant) => (grant.to.kind === "user" ? [grant.to.id] : [])),
  );
  const people = [
    ...new Set([
      ...(granted ?? []).flatMap((grant) =>
        grant.on.kind === "workspace" && grant.to.kind === "user" ? [grant.to.id] : [],
      ),
      ...(members ?? []).flatMap((member) => (member.kind === "user" ? [member.id] : [])),
    ]),
  ]
    .filter((person) => !holding.has(person))
    .sort();
  /** A change to access, done or not, after which grantr's answers in the tenant are read again. */
  const changed = <A,>(answer: Promise<A>) => changedAccess(queryClient, tenant, answer);
  const canShare = allowed.has("grantr:grant");
  return (
    <div className="flex flex-col items-end gap-1">
      {isRestricted && (
        <p className="text-muted text-sm">Restricted to the people it's shared with</p>
      )}
      <ThreadMenu
        restricted={isRestricted}
        triggerRef={trigger}
        onRestrict={() =>
          changed(commands.grantr.restrict(tenant, { on, restricted: !isRestricted }))
        }
        onShare={canShare ? () => setSharing(true) : null}
      />
      {canShare && (
        <ShareDialog
          open={sharing}
          onOpenChange={setSharing}
          grants={held}
          people={people}
          canRevoke={allowed.has("grantr:revoke")}
          finalFocus={trigger}
          onGrant={(person, role) =>
            changed(commands.grantr.grant(tenant, { role, on, to: { kind: "user", id: person } }))
          }
          onRevoke={(grant) =>
            changed(
              commands.grantr.revoke(tenant, { role: grant.role, on: grant.on, to: grant.to }),
            )
          }
        />
      )}
    </div>
  );
}
