import {
  type Artifactr,
  type ArtifactrV1,
  allowedIn,
  changedAccess,
  type GrantrApi,
  thumbs,
  useMe,
  usePeople,
  workspaceOf,
} from "@portalr/client";
import {
  Alert,
  ASK_FORM,
  ASK_USER,
  ButtonLink,
  Composer,
  ComposerDock,
  CRUMB,
  Message,
  Messages,
  NotFound as NotFoundPage,
  PageHeader,
  ProposalCard,
  Questions,
  Request,
  RunFailed,
  RunSteps,
  RunStrip,
  rendererFor,
  Streaming,
} from "@portalr/ui";
import {
  type UseSuspenseQueryOptions,
  useSuspenseQueries,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { CatchBoundary, createFileRoute, Link } from "@tanstack/react-router";
import { type ReactNode, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { author, unnamedPeople } from "../../../../../../../author";
import { usePosting } from "../../../../../../../posting";
import { RENDERERS } from "../../../../../../../renderers";
import { ShareDialog } from "../../../../../../../share-dialog";
import { ThreadArtifact } from "../../../../../../../thread-artifact";
import { RETRY_TAKEN, retryOf, threadLog } from "../../../../../../../thread-log";
import { ThreadMenu } from "../../../../../../../thread-menu";
import { Uploader } from "../../../../../../../upload";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/**
 * What a person may do with a thread, asked of grantr on the thread itself: reading it, which a
 * restriction takes away while it's open, posting in it, and changing who sees it.
 */
const ACTIONS = [
  "artifactr:read_threads",
  "artifactr:post_message",
  "artifactr:stop_run",
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
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Thread · ${params.workspace}`) }],
  }),
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

function Chat() {
  const { tenant, workspace, thread: id } = Route.useParams();
  const crumbs = [
    {
      label: "Threads",
      render: (
        <Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} activeOptions={CRUMB} />
      ),
    },
  ];
  const context = Route.useRouteContext();
  const { queries, queryClient, user, config } = context;
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
  const { threads, runs, proposals, artifacts } = snapshot.state;
  const thread = threads[id];
  const { posting, post } = usePosting(thread?.messages);
  // Files dropped on the composer, for the uploader it holds (portalr ADR-0080).
  const [dropped, setDropped] = useState<FileList | null>(null);
  // The people who posted without a name of their own, named when drawn: the stream's state
  // holds the actors as the server sent them, never an email.
  const names = usePeople(
    queries,
    config.people,
    tenant,
    unnamedPeople(
      [
        ...(thread?.messages ?? []),
        ...Object.values(runs).flatMap((run) =>
          run.threadId === id
            ? [...run.answered, ...run.questions.flatMap(({ answer }) => answer ?? [])]
            : [],
        ),
      ],
      me,
    ),
  );
  // The requests already waiting when this thread is first shown live: they don't take the focus,
  // which starts at the page's heading; one that arrives while the page is open does (portalr
  // ADR-0068). Kept with the thread's id, so another thread's page starts afresh.
  const [atLoad, setAtLoad] = useState<{ id: string; waiting: ReadonlySet<string> } | null>(null);
  useEffect(() => {
    if (snapshot.status === "live" && atLoad?.id !== id) {
      setAtLoad({
        id,
        waiting: new Set(
          Object.values(runs)
            .filter((run) => run.threadId === id)
            .flatMap((run) => run.requests.map((request) => request.tool_call_id)),
        ),
      });
    }
  }, [snapshot.status, runs, id, atLoad]);
  if (thread === undefined) {
    return snapshot.status === "live" ? (
      <NotFoundPage
        title="Thread not found"
        action={
          <ButtonLink render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}>
            All threads
          </ButtonLink>
        }
      >
        There's no thread here by that name, or it isn't one you can see.
      </NotFoundPage>
    ) : (
      <Connection snapshot={snapshot} waiting="the thread" />
    );
  }
  if (!allowed.has("artifactr:read_threads")) {
    return (
      <>
        <PageHeader title={thread.title || "Untitled"} breadcrumbs={crumbs} />
        <Alert tone="error">This isn't available to you any more.</Alert>
      </>
    );
  }
  const active = Object.values(runs).filter(
    (run) => run.threadId === id && (run.status === "running" || run.status === "paused"),
  );
  const proposed = Object.values(proposals).filter((proposal) => proposal.threadId === id);
  // The artifacts made here whose kind the thread shows, each once, where it was made.
  const inline = Object.values(artifacts).filter(
    (artifact) => artifact.threadId === id && rendererFor(artifact.kind, RENDERERS).inline,
  );

  const give = (message: Artifactr.Message) => (up: boolean, comment: string | null) =>
    stream.send({
      type: "give_feedback",
      feedback_type: "thumbs",
      target: { kind: "message", thread_id: id, message_id: message.id, run_id: message.runId },
      value: comment === null ? { up } : { up, comment },
    });
  const answer =
    (run: Artifactr.Run, request: ArtifactrV1.DeferredRequest) =>
    (answered: Omit<ArtifactrV1.AnswerDeferred, "type" | "run_id" | "tool_call_id">) =>
      stream.send({
        type: "answer_deferred",
        run_id: run.id,
        tool_call_id: request.tool_call_id,
        ...answered,
      });
  /** Post a message, under `messageId` where it has one already: a retry's, or one unsent. */
  const send = async (content: string, messageId?: string) => {
    const sent = await post(
      content,
      (message_id) => stream.send({ type: "post_message", thread_id: id, content, message_id }),
      messageId,
    );
    if (sent.outcome === "refused") {
      // Refused, perhaps since they may no longer post or read it: ask grantr again.
      void queryClient.invalidateQueries({ queryKey: checks.queryKey });
    }
    return sent;
  };
  const log = threadLog(thread, runs, inline);
  // The thread's latest turn, if it failed, can be tried again by whoever may post.
  const retry = allowed.has("artifactr:post_message") ? retryOf(thread, runs, me) : null;
  const latestRequest = active.flatMap((run) => run.requests).at(-1);
  const arrived =
    latestRequest !== undefined &&
    atLoad?.id === id &&
    !atLoad.waiting.has(latestRequest.tool_call_id);
  // To the question's own named part, such as "The agent asks", or else to where it is.
  const toQuestion = () => {
    const at = document.getElementById(`request-${latestRequest?.tool_call_id}`);
    const named = at?.querySelector<HTMLElement>("[aria-label], [aria-labelledby]") ?? at;
    if (named && !named.hasAttribute("tabindex")) {
      named.tabIndex = -1;
    }
    named?.focus();
  };

  return (
    <section
      aria-labelledby="thread"
      data-portalr-replay="block"
      className="flex max-w-190 flex-col gap-6"
    >
      <PageHeader
        title={thread.title || "Untitled"}
        breadcrumbs={crumbs}
        id="thread"
        actions={
          <>
            {(allowed.has("grantr:grant") || allowed.has("grantr:restrict")) && (
              <CatchBoundary
                getResetKey={() => id}
                errorComponent={() => (
                  <Alert tone="error">Who has access to it couldn't be read.</Alert>
                )}
              >
                <Suspense fallback={null}>
                  <Access tenant={tenant} workspace={workspace} thread={id} allowed={allowed} />
                </Suspense>
              </CatchBoundary>
            )}
          </>
        }
      />
      <Connection snapshot={snapshot} waiting="the thread" />
      <Messages>
        {log.map((entry) => {
          switch (entry.kind) {
            case "message":
              return (
                <Message
                  key={entry.message.id}
                  message={entry.message}
                  author={author(entry.message.actor, me, names)}
                  mine={entry.message.actor.kind === "user" && entry.message.actor.id === me}
                  thumbs={thumbs(entry.message.feedback, me)}
                  {...(entry.message.runId !== null && { onThumbs: give(entry.message) })}
                />
              );
            case "tools":
              return (
                <RunSteps
                  key={entry.tools[0]?.[0]}
                  tools={entry.tools}
                  running={entry.run.status === "running"}
                />
              );
            case "question": {
              const { request, answer: given } = entry.question;
              return (
                <li
                  key={request.tool_call_id}
                  id={`request-${request.tool_call_id}`}
                  tabIndex={-1}
                  className="outline-none"
                >
                  <Questions
                    request={request}
                    answer={given?.value ?? null}
                    answeredBy={given ? author(given.actor, me, names) : null}
                    focus={request === latestRequest && arrived}
                    onAnswer={(value) => answer(entry.run, request)({ answer: value })}
                  />
                </li>
              );
            }
            case "artifact":
              return (
                <ThreadArtifact
                  key={entry.artifact.id}
                  context={context}
                  me={me}
                  tenant={tenant}
                  workspace={workspace}
                  artifact={entry.artifact}
                />
              );
            case "failed":
              return (
                <RunFailed
                  key={entry.run.id}
                  reason={entry.run.reason}
                  // What it failed with, which may name the reader's own words, is its author's.
                  error={entry.run.actsFor === me ? entry.run.error : null}
                  {...(retry?.run === entry.run.id &&
                    (retry.id === null
                      ? { retryRefused: RETRY_TAKEN }
                      : { onRetry: () => send(retry.content, retry.id) }))}
                />
              );
            default:
              return entry satisfies never;
          }
        })}
        {posting.map(({ id: posted, content, unsent }) => (
          <Message
            key={posted}
            message={{
              id: posted,
              seq: snapshot.seq,
              actor: { kind: "user", id: me },
              content,
              kind: "message",
              runId: null,
              feedback: [],
            }}
            author="You"
            mine
            sending
            {...(unsent && { onSendAgain: () => send(content, posted) })}
          />
        ))}
        {active
          .filter((run) => run.status === "running")
          .map((run) => (
            <Streaming key={run.id} text={run.text} author="Assistant" />
          ))}
      </Messages>
      {active.map((run) => (
        <div key={run.id} className="flex flex-col gap-2">
          <RunStrip
            run={run}
            {...(run.status === "running" &&
              allowed.has("artifactr:stop_run") && {
                onStop: () => stream.send({ type: "stop_run", run_id: run.id }),
              })}
            {...(run.requests.length > 0 && { onQuestion: toQuestion })}
          />
          {[
            ...run.requests
              .filter((request) => request.tool_name !== ASK_USER)
              .map((request) => ({ request, by: undefined })),
            // A form stays where it was asked once it is answered, until its run ends, and says by whom.
            ...run.answered
              .filter(({ request }) => request.tool_name === ASK_FORM)
              .map(({ request, actor }) => ({ request, by: author(actor, me, names) })),
          ].map(({ request, by }) => (
            <div
              key={request.tool_call_id}
              id={`request-${request.tool_call_id}`}
              tabIndex={-1}
              className="outline-none"
            >
              <Request
                request={request}
                {...(by !== undefined && { answeredBy: by })}
                // The newest request waiting takes the focus if it arrived while the page was
                // open, never one already answered, nor one waiting when the page was shown.
                focus={request === latestRequest && arrived}
                onAnswer={answer(run, request)}
              />
            </div>
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
        <ComposerDock>
          <Composer
            disabled={snapshot.status !== "live"}
            onSend={send}
            onFiles={setDropped}
            attach={
              <Uploader
                context={context}
                tenant={tenant}
                workspace={workspace}
                thread={id}
                attach
                files={dropped}
              />
            }
          />
        </ComposerDock>
      )}
      {snapshot.status !== "closed" && !allowed.has("artifactr:post_message") && (
        <Uploader context={context} tenant={tenant} workspace={workspace} thread={id} />
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
  const { commands, queryClient, queries, config } = Route.useRouteContext();
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
  const names = usePeople(queries, config.people, tenant, [
    ...people,
    ...(held ?? []).flatMap((grant) => (grant.to.kind === "user" ? [grant.to.id] : [])),
  ]);
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
          names={names}
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
