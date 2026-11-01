/**
 * An approval as a person reads it, before they answer and after (lattice RFC-0011, grantr
 * ADR-0040). The app's page for it and admin's confirm page both show it so; each has its own
 * buttons.
 */

import type { GrantrApi } from "@portalr/client";
import { unhidden } from "./hidden";
import { Moment } from "./moment";
import { StatusBadge, type Tone } from "./status-badge";

type Approval = GrantrApi.components["schemas"]["ApprovalView"];

/** Where an approval stands, in a word, with its badge's tone. */
const STANDING: Readonly<Record<Approval["state"], { word: string; tone: Tone }>> = {
  pending: { word: "Waiting", tone: "waiting" },
  approved: { word: "Approved", tone: "done" },
  denied: { word: "Denied", tone: "stopped" },
  expired: { word: "Expired", tone: "stopped" },
  withdrawn: { word: "Withdrawn", tone: "stopped" },
};

/** Where an approval stands, as a badge: in a word, a shape and a colour. */
export function ApprovalStanding({ state }: { state: Approval["state"] }) {
  const { word, tone } = STANDING[state];
  return <StatusBadge tone={tone}>{word}</StatusBadge>;
}

/**
 * Text of the call's, as it is, under its label: in the mono face, scrolled sideways rather than
 * wrapped, and each character a reader wouldn't see shown as its code point. Plain, not
 * highlighted, so neither page loads the highlighter for it.
 */
function Shown({ label, children }: { label: string; children: string }) {
  return (
    <section aria-label={label} className="flex flex-col gap-1">
      <p className="text-muted text-sm">{label}</p>
      <pre className="overflow-x-auto rounded-(--code-block-radius) border border-line bg-paper p-(--code-panel-pad) font-mono text-xs">
        {unhidden(children)}
      </pre>
    </section>
  );
}

/**
 * What an approval asks, and where it stands, for a person to read before they answer:
 *
 * - more of what the call does, where its title isn't enough;
 * - the change it would make, as a diff, or else the call's arguments;
 * - the steps of a plan it would pre-approve, if it is a plan's;
 * - who asked, the capability and its version, the workspace, and when it was asked;
 * - who may answer it and when it expires, while it waits, or else who answered, when, on which
 *   page, and why.
 *
 * Each character a reader wouldn't see in the server's text is shown as its code point, so what
 * is read is what the call would do. Its title is the page's to show, as its heading.
 */
export function ApprovalDetails({
  approval,
  askedBy,
  answeredBy,
  answerers,
}: {
  approval: Approval;
  /** Who asked, in words, as the client's `askedBy` says. */
  askedBy: string;
  /** Who answered, in words, as the client's `answeredBy` says, if anyone has. */
  answeredBy?: string | undefined;
  /** Who may answer, in words, as the client's `answerersOf` says: shown while it waits. */
  answerers?: readonly string[] | undefined;
}) {
  const { rendering, answer } = approval;
  return (
    <div className="flex flex-col gap-4">
      {rendering.summary !== "" && <p>{unhidden(rendering.summary)}</p>}
      {rendering.diff == null ? (
        <Shown label="What it would be called with">
          {JSON.stringify(rendering.arguments ?? {}, null, 2)}
        </Shown>
      ) : (
        <Shown label="The change it would make">{rendering.diff}</Shown>
      )}
      {approval.covers.length > 0 && (
        <section aria-label="The plan's steps it allows" className="flex flex-col gap-1">
          <p>Approving it allows these steps of the plan, and no others:</p>
          <ul className="list-disc ps-5">
            {approval.covers.map((step) => (
              <li key={step.digest}>
                <code className="font-mono">{step.capability}</code>
                {` at step ${step.step}`}
                {step.max_calls == null ? "" : `, at most ${step.max_calls} times`}
              </li>
            ))}
          </ul>
        </section>
      )}
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">Asked by</dt>
        <dd>{askedBy}</dd>
        <dt className="text-muted">Capability</dt>
        <dd>
          <code className="font-mono">{approval.capability}</code>
          {` ${approval.version}`}
        </dd>
        <dt className="text-muted">Workspace</dt>
        <dd>{approval.scope.workspace_id}</dd>
        <dt className="text-muted">Asked</dt>
        <dd>
          <Moment at={approval.asked_at} />
        </dd>
        {approval.state === "pending" && answerers !== undefined && answerers.length > 0 && (
          <>
            <dt className="text-muted">Who may answer</dt>
            <dd>{answerers.join(", ")}</dd>
          </>
        )}
        {approval.state === "pending" && (
          <>
            <dt className="text-muted">Expires</dt>
            <dd>
              <Moment at={approval.deadline} />
            </dd>
          </>
        )}
        {answer != null && (
          <>
            <dt className="text-muted">{answer.approved ? "Approved by" : "Denied by"}</dt>
            <dd>
              {answeredBy ?? answer.by.id}
              {", "}
              <Moment at={answer.at} />
              {answer.surface === "portalr:confirm" ? ", on the confirm page" : ""}
            </dd>
            {answer.reason != null && (
              <>
                <dt className="text-muted">Why</dt>
                <dd>{unhidden(answer.reason)}</dd>
              </>
            )}
          </>
        )}
        {approval.reason != null && (
          <>
            <dt className="text-muted">Why</dt>
            <dd>{unhidden(approval.reason)}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
