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
  firedOf,
  Message,
  Messages,
  ModeSwitch,
  NotFound as NotFoundPage,
  PageHeader,
  ProposalCard,
  prefetchStreaming,
  proposedOn,
  Questions,
  Request,
  RunFailed,
  RunSteps,
  RunStrip,
  rendererFor,
  SelectField,
  StatusBadge,
  Streaming,
  ThumbBar,
  useLoaded,
} from "@portalr/ui";
import {
  type UseSuspenseQueryOptions,
  useSuspenseQueries,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { CatchBoundary, createFileRoute, Link, useRouterState } from "@tanstack/react-router";
import {
  type ReactNode,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { author, unnamedPeople } from "../../../../../../../author";
import { ComposerFooter } from "../../../../../../../composer-footer";
import { usePosting } from "../../../../../../../posting";
import { RENDERERS } from "../../../../../../../renderers";
import { RuleProposal } from "../../../../../../../rule-proposal";
import { markSeen } from "../../../../../../../seen";
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
  "artifactr:set_thread_mode",
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

/** The composer's choice of model, loaded as the composer first takes the focus (portalr ADR-0086). */
const loadPicker = () => import("../../../../../../../on-demand/model-picker");
/** From this width a thread's artifact, and an approval, sit beside it (portalr ADR-0087). */
const SPLIT = "(min-width: 1100px)";
const splitChanges = (changed: () => void) => {
  const query = matchMedia(SPLIT);
  query.addEventListener("change", changed);
  return () => query.removeEventListener("change", changed);
};

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
  const wide = useSyncExternalStore(splitChanges, () => matchMedia(SPLIT).matches);
  // Files dropped on the composer, for the uploader it holds (portalr ADR-0080).
  const [dropped, setDropped] = useState<FileList | null>(null);
  // The model the next message names, or null for the default (portalr ADR-0086): the models,
  // and the picker, are read the first time the composer takes the focus, never as the page loads.
  const [focused, setFocused] = useState(false);
  const composer = useRef<HTMLDivElement>(null);
  // After every render, not once: the composer is drawn only once the thread is, and may go.
  useEffect(() => {
    const box = composer.current;
    if (focused || box === null) {
      return;
    }
    const heard = () => setFocused(true);
    box.addEventListener("focusin", heard);
    return () => box.removeEventListener("focusin", heard);
  });
  const [model, setModel] = useState<string | null>(null);
  const picker = useLoaded(loadPicker, focused).module;
  const place = { api: context.api, tenant, workspace };
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
  const [atLoad, setAtLoad] = useState<{
    id: string;
    waiting: ReadonlySet<string>;
    /** The log's position as the thread was shown live: what ends after it happened here. */
    seq: number;
  } | null>(null);
  useEffect(() => {
    if (snapshot.status === "live" && atLoad?.id !== id) {
      setAtLoad({
        id,
        seq: snapshot.seq,
        waiting: new Set(
          Object.values(runs)
            .filter((run) => run.threadId === id)
            .flatMap((run) => run.requests.map((request) => request.tool_call_id)),
        ),
      });
    }
  }, [snapshot.status, runs, id, atLoad]);
  // What a turn shows as it streams is loaded ahead of the first (portalr ADR-0083).
  useEffect(() => prefetchStreaming(), []);
  // The thread before a turn, as sent to the model, for its token estimate (portalr ADR-0083):
  // the characters of the messages before the turn's start, summed as the strip is drawn.
  const sentBefore = (started: number) =>
    (thread?.messages ?? []).reduce(
      (chars, message) => (message.seq < started ? chars + message.content.length : chars),
      0,
    );
  // How far this browser has read the thread: where it is active at, once shown live (portalr
  // ADR-0080), for the list's mark of what has moved since.
  const readTo = thread?.active;
  useEffect(() => {
    if (snapshot.status !== "live" || readTo === undefined) {
      return;
    }
    // A tab out of sight hasn't been read: marked as it comes into view.
    const mark = () => {
      if (document.visibilityState === "visible") {
        markSeen(tenant, workspace, id, readTo);
      }
    };
    mark();
    document.addEventListener("visibilitychange", mark);
    return () => document.removeEventListener("visibilitychange", mark);
  }, [snapshot.status, tenant, workspace, id, readTo]);
  // Opened at a request, as from Needs you (portalr ADR-0080): once the thread is shown live, the
  // page goes to it, as Go to the question does.
  const hash = useRouterState({ select: (state) => state.location.hash });
  useEffect(() => {
    if (atLoad?.id === id && hash.startsWith("request-")) {
      toRequest(hash.slice("request-".length));
    }
  }, [atLoad, id, hash]);
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
      <Connection snapshot={snapshot} onReconnect={stream.reconnect} waiting="the thread" />
    );
  }
  if (!allowed.has("artifactr:read_threads")) {
    return (
      <>
        <PageHeader title={thread.title || "Untitled"} />
        <Alert tone="error">This isn't available to you any more.</Alert>
      </>
    );
  }
  const active = Object.values(runs).filter(
    (run) => run.threadId === id && (run.status === "running" || run.status === "paused"),
  );
  const proposed = Object.values(proposals).filter((proposal) => proposal.threadId === id);
  /** The thread's open proposal that would change an artifact, if there is one. */
  const waitingOn = (artifact: string) =>
    proposed.find((proposal) => proposal.status === "open" && proposedOn(proposal) === artifact)
      ?.id ?? null;
  // The artifacts made here whose kind the thread shows, each once, where it was made.
  const inline = Object.values(artifacts).filter(
    (artifact) => artifact.threadId === id && rendererFor(artifact.kind, RENDERERS).inline,
  );
  // Wide, the thread's latest artifact and what waits for approval sit beside it, in a pane of
  // their own, the approval's Deny and Approve in its corner (portalr ADR-0087).
  const approvals = active.flatMap((run) =>
    run.requests.flatMap((request) => (request.kind === "approval" ? [{ run, request }] : [])),
  );
  const beside = wide
    ? inline.reduce<(typeof inline)[number] | undefined>(
        (latest, artifact) => (latest && latest.seq > artifact.seq ? latest : artifact),
        undefined,
      )
    : undefined;
  const split = beside !== undefined || (wide && approvals.length > 0);

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
      (message_id) =>
        stream.send({
          type: "post_message",
          thread_id: id,
          content,
          message_id,
          ...(model !== null && { model }),
        }),
      messageId,
    );
    if (sent.outcome === "refused") {
      // Refused, perhaps since they may no longer post or read it: ask grantr again.
      void queryClient.invalidateQueries({ queryKey: checks.queryKey });
    }
    return sent;
  };
  const log = threadLog(thread, runs, inline, artifacts);
  // The thread's latest turn, if it failed, can be tried again by whoever may post.
  const retry = allowed.has("artifactr:post_message") ? retryOf(thread, runs, me) : null;
  const latestRequest = active.flatMap((run) => run.requests).at(-1);
  const arrived =
    latestRequest !== undefined &&
    atLoad?.id === id &&
    !atLoad.waiting.has(latestRequest.tool_call_id);
  const toQuestion = () => toRequest(latestRequest?.tool_call_id);
  // The agent's mode, where the reader may set it: in the composer's row, or alone without one.
  const mode = allowed.has("artifactr:set_thread_mode") && (
    <ModeSwitch
      mode={thread.mode}
      disabled={snapshot.status !== "live"}
      onChange={(chosen) => stream.send({ type: "set_thread_mode", thread_id: id, mode: chosen })}
    />
  );

  const canPost = snapshot.status !== "closed" && allowed.has("artifactr:post_message");
  // A turn's strip, while it works or waits on a question: while it works, above the composer,
  // where the reader writes and stops it (portalr ADR-0087); while it waits, above what it asks,
  // which a phone's thumb bar answers. An approval waits in its own card, which says so: no strip
  // above it too (ADR-0085).
  const strip = (run: Artifactr.Run) =>
    (run.status === "running" || run.requests.some((request) => request.kind !== "approval")) && (
      <RunStrip
        key={run.id}
        run={run}
        history={sentBefore(run.started)}
        {...(run.status === "running" &&
          allowed.has("artifactr:stop_run") && {
            onStop: () => stream.send({ type: "stop_run", run_id: run.id }),
          })}
        // The way to what is asked, a question up the log or a form, which may be long; an
        // approval sits short under the strip, and needs none (portalr ADR-0085).
        {...(run.requests.some((request) => request.kind !== "approval") && {
          onQuestion: toQuestion,
        })}
      />
    );
  const asked = (
    run: Artifactr.Run,
    request: ArtifactrV1.DeferredRequest,
    by: string | undefined,
  ) => (
    <div
      key={request.tool_call_id}
      id={`request-${request.tool_call_id}`}
      tabIndex={-1}
      // An approval waiting holds the window's foot, over what is above it, with the composer's
      // dock in the flow under it, so Deny and Approve are never off screen or covered (ADR-0087).
      className={
        request.kind === "approval" && !split
          ? "sticky bottom-0 z-10 rounded-(--card-radius) shadow-(--dialog-shadow) outline-none"
          : "outline-none"
      }
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
  );
  const chat = (
    <section
      aria-labelledby="thread"
      data-portalr-replay="block"
      // The composer at the window's foot, under however few messages (portalr ADR-0087).
      className={`flex min-w-0 flex-1 flex-col gap-6 ${split ? "" : "mx-auto w-full max-w-190"}`}
    >
      <PageHeader
        title={thread.title || "Untitled"}
        id="thread"
        actions={
          (allowed.has("grantr:grant") || allowed.has("grantr:restrict")) && (
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
          )
        }
      />
      <Connection snapshot={snapshot} onReconnect={stream.reconnect} waiting="the thread" />
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
              return entry.artifact === beside ? null : (
                <ThreadArtifact
                  key={entry.updatedBy ? `call:${entry.updatedBy}` : `art:${entry.artifact.id}`}
                  context={context}
                  me={me}
                  tenant={tenant}
                  workspace={workspace}
                  artifact={entry.artifact}
                  fired={firedOf(Object.values(proposals), entry.artifact.id)}
                  waiting={waitingOn(entry.artifact.id)}
                  {...(entry.superseded && { superseded: entry.superseded })}
                />
              );
            case "partial":
              return [
                (entry.run.text !== "" || entry.run.live.thinking !== "") && (
                  <Streaming
                    key={`${entry.run.id}-partial`}
                    text={entry.run.text}
                    live={entry.run.live}
                    ended={entry.run.status}
                    author="Assistant"
                  />
                ),
                // A line of the log, which announces it: the one end nothing else says, as the
                // status mark and word the Runs page shows (portalr ADR-0085).
                entry.run.status === "stopped" && (
                  <li key={`${entry.run.id}-stopped`} className="self-start">
                    <StatusBadge tone="stopped">Stopped</StatusBadge>
                  </li>
                ),
              ];
            case "failed":
              return (
                <RunFailed
                  key={entry.run.id}
                  reason={entry.run.reason}
                  // What it failed with, which may name the reader's own words, is its author's.
                  error={entry.run.actsFor === me ? entry.run.error : null}
                  // One that failed while the page was open is announced, whoever started it.
                  live={(atLoad?.id === id && (entry.run.ended ?? 0) > atLoad.seq) || undefined}
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
            <Streaming key={run.id} text={run.text} live={run.live} author="Assistant" />
          ))}
      </Messages>
      {active.map((run) => (
        // In the thread's own flow, so a waiting approval's card can hold the window's foot.
        <div key={run.id} className="contents">
          {(!canPost || run.status !== "running") && strip(run)}
          {picker && <picker.AnsweredBy place={place} run={run} />}
          {[
            ...run.requests
              .filter(
                (request) =>
                  request.tool_name !== ASK_USER && !(split && request.kind === "approval"),
              )
              .map((request) => ({ request, by: undefined })),
            // A form stays where it was asked once it is answered, until its run ends, and says by whom.
            ...run.answered
              .filter(({ request }) => request.tool_name === ASK_FORM)
              .map(({ request, actor }) => ({ request, by: author(actor, me, names) })),
          ].map(({ request, by }) => asked(run, request, by))}
        </div>
      ))}
      {proposed.map((proposal) => (
        // Where a file created blank links to the change that fills it.
        <div
          key={proposal.id}
          id={`proposal-${proposal.id}`}
          tabIndex={-1}
          className="outline-none"
        >
          <ProposalCard
            proposal={proposal}
            onRespond={(decision) =>
              stream.send({ type: "respond_to_proposal", proposal_id: proposal.id, decision })
            }
          >
            <RuleProposal
              proposal={proposal}
              kind={artifacts[proposedOn(proposal) ?? ""]?.kind}
              place={{ context, tenant, workspace }}
            />
          </ProposalCard>
        </div>
      ))}
      {canPost && (
        // While an approval waits in the column, the dock stays in the flow under it, so it never
        // covers Deny and Approve (portalr ADR-0087).
        <ComposerDock
          className={`mt-auto flex flex-col gap-2 ${approvals.length > 0 && !split ? "static" : ""}`}
        >
          {active.filter((run) => run.status === "running").map(strip)}
          {/* The composer's first focus loads the model picker (portalr ADR-0086). */}
          <div className="contents" ref={composer}>
            <Composer
              onSend={send}
              onFiles={setDropped}
              attach={
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
                  <Uploader
                    context={context}
                    tenant={tenant}
                    workspace={workspace}
                    thread={id}
                    attach
                    files={dropped}
                  />
                  {/* The agent's mode, a setting of the thread's, beside what is sent to it (portalr
                      ADR-0085); on a phone it is in the "+" sheet, said when it isn't the default. */}
                  <span className="contents phone:hidden">{mode}</span>
                  <ComposerFooter
                    api={context.api}
                    tenant={tenant}
                    workspace={workspace}
                    thread={id}
                    focused={focused}
                    model={model}
                    onModel={setModel}
                    running={active.length > 0}
                    mode={thread.mode}
                    onMode={
                      allowed.has("artifactr:set_thread_mode")
                        ? (chosen) =>
                            stream.send({ type: "set_thread_mode", thread_id: id, mode: chosen })
                        : undefined
                    }
                    onFiles={setDropped}
                  />
                  {/* A phone's thumb bar: the request's next step, at the row's end (portalr ADR-0082). */}
                  {latestRequest !== undefined && (
                    <ThumbBar target={`request-${latestRequest.tool_call_id}`} />
                  )}
                  {/* The model's choice last: where the row is narrow it wraps to a line of its own (portalr ADR-0087). */}
                  {/* A select on a desktop; on a phone the pill and its sheet (portalr ADR-0087). */}
                  <span className="contents phone:hidden">
                    {picker && (
                      <picker.ModelPicker
                        place={place}
                        thread={id}
                        value={model}
                        onChange={setModel}
                        running={active.length > 0}
                        Select={SelectField}
                      />
                    )}
                  </span>
                </div>
              }
            />
          </div>
        </ComposerDock>
      )}
      {snapshot.status !== "closed" && !allowed.has("artifactr:post_message") && (
        <>
          {/* Who may set the mode but not post has it on its own, where the composer would be. */}
          {mode}
          <Uploader context={context} tenant={tenant} workspace={workspace} thread={id} />
        </>
      )}
    </section>
  );
  return split ? (
    <div className="grid flex-1 grid-cols-2 gap-8">
      {chat}
      <aside
        aria-label="Beside the thread"
        className="sticky top-(--header-clearance) -my-6 flex self-start h-[calc(100dvh-var(--header-clearance))] flex-col gap-4 overflow-y-auto border-line border-s py-6 ps-8"
      >
        {beside && (
          <ul>
            <ThreadArtifact
              context={context}
              me={me}
              tenant={tenant}
              workspace={workspace}
              artifact={beside}
              waiting={waitingOn(beside.id)}
            />
          </ul>
        )}
        {approvals.length > 0 && (
          <div className="sticky bottom-0 mt-auto ms-auto flex w-full max-w-md flex-col gap-2 shadow-(--dialog-shadow)">
            {approvals.map(({ run, request }) => asked(run, request, undefined))}
          </div>
        )}
      </aside>
    </div>
  ) : (
    chat
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
    <div className="flex items-center gap-2">
      {isRestricted && (
        <p className="text-muted text-xs">
          Restricted<span className="sr-only"> to the people it's shared with</span>
        </p>
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

/** To a request's own named part, such as "The agent asks", or else to where it is. */
function toRequest(toolCallId: string | undefined) {
  const at = document.getElementById(`request-${toolCallId}`);
  const named = at?.querySelector<HTMLElement>("[aria-label], [aria-labelledby]") ?? at;
  if (named && !named.hasAttribute("tabindex")) {
    named.tabIndex = -1;
  }
  named?.focus();
}
