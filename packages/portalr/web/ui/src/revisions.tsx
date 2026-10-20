/**
 * An artifact's revisions, readable (portalr ADR-0054): newest first, each a disclosure whose
 * summary says which version it is, who made it, when, and what it changed, the latest open and
 * the rest closed. Open, a revision shows its kind's title and summary where it has them, then
 * its Preview, its Source and its Changes, as tabs: its content through its kind's renderer, its
 * sources numbered and highlighted, and what changed since the version before, part by part, a
 * source's line by line and a title's word by word. A kind whose preview runs what it holds, a mini
 * app, runs one revision at a time, when asked, and only where apps run; what is done in a preview
 * is not saved.
 */

import { Tabs } from "@base-ui/react/tabs";
import type { Change, Granularity } from "@portalr/client";
import { ChevronRight, Play, Square } from "lucide-react";
import { createContext, type ReactNode, use, useId, useMemo, useState } from "react";
import { type AppHost, AppHostContext, MINI_APPS, stillWhy } from "./app-frame";
import {
  type Data,
  Diff,
  partsOf,
  type Renderer,
  type Renderers,
  type RevisionPart,
  rendererFor,
  ShownContext,
} from "./artifacts";
import { Button } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";
import { IntegrationsContext } from "./integrations";
import { LineDiff, lineCounts } from "./line-diff";
import { ago } from "./moment";
import { SourceView } from "./source-view";
import { TYPE } from "./type";

/** A revision, as a list of them shows it. */
export interface RevisionShown {
  readonly version: number;
  readonly kind: string;
  readonly data: Data;
  /** Who made it, as the page names them: "You", a person's name, "Assistant". */
  readonly by: string;
  /** When it was made, as RFC 3339 writes it; a revision saved before it was dated has none. */
  readonly at?: string | null;
}

/** How two texts differ: `client`'s `changes`, which the page gives. */
export type Compare = (before: string, after: string, by: Granularity) => Change[] | null;

/** A part that changed since the version before, and how. */
interface Changed {
  readonly part: RevisionPart;
  readonly changes: Change[] | null;
}

/** What a revision changed, part by part, since the version before it, or null for the first. */
function changedParts(
  renderer: Renderer,
  data: Data,
  before: Data | null,
  compare: Compare,
): Changed[] | null {
  if (before === null) {
    return null;
  }
  const was = new Map(partsOf(renderer, before).map((part) => [part.name, part.text]));
  return partsOf(renderer, data).flatMap((part) => {
    const earlier = was.get(part.name) ?? "";
    return earlier === part.text ? [] : [{ part, changes: compare(earlier, part.text, part.diff) }];
  });
}

/** What a revision changed, in a line: "First version", "Changed the title and the HTML (+3 −1)". */
export function changedSaid(changed: readonly Changed[] | null): string {
  if (changed === null) {
    return "First version";
  }
  if (changed.length === 0) {
    return "No change to its content";
  }
  const each = changed.map(({ part, changes }) => {
    if (part.diff === "words" || changes === null) {
      return `the ${part.name}`;
    }
    const { added, removed } = lineCounts(changes);
    return `the ${part.name} (+${added} −${removed})`;
  });
  const listed = each.length === 1 ? each[0] : `${each.slice(0, -1).join(", ")} and ${each.at(-1)}`;
  return `Changed ${listed}`;
}

/** Which revision's preview runs, of a list's: one at a time. */
const RunningRevision = createContext<{
  readonly version: number | null;
  readonly run: (version: number | null) => void;
}>({ version: null, run: () => {} });

/**
 * The host a preview runs under: the page's apps' origin, its state kept in the frame and never
 * written, and nothing submitted, so running an old version changes nothing.
 */
function previewHost(host: AppHost): AppHost {
  return {
    origin: host.origin,
    setState: () => Promise.resolve({ outcome: "done" }),
    submit: () => Promise.resolve({ outcome: "refused" }),
  };
}

/** Whether a kind's preview may run here: apps on in the workspace, and an origin of their own. */
function useRunsHere(): boolean {
  const host = use(AppHostContext);
  const on = use(IntegrationsContext)(MINI_APPS);
  return stillWhy({ id: "", version: 0 }, !on, host) === null;
}

/** A revision's preview of a kind that runs what it holds: run on asking, one at a time. */
function RunPreview({ id, revision, renderer }: Previewed) {
  const host = use(AppHostContext);
  const running = use(RunningRevision);
  const preview = useMemo(() => host && previewHost(host), [host]);
  const live = running.version === revision.version;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => running.run(live ? null : revision.version)}
        >
          <Icon icon={live ? Square : Play} className="size-3.5" />
          {live ? `Stop version ${revision.version}` : `Run version ${revision.version}`}
        </Button>
        <p className={TYPE.note}>
          One version runs at a time. What you do in a preview isn't saved.
        </p>
      </div>
      {live && preview && (
        <AppHostContext value={preview}>
          <ShownContext value={{ id, version: revision.version, archived: false }}>
            {renderer.preview?.(revision.data) ?? renderer.render(revision.data)}
          </ShownContext>
        </AppHostContext>
      )}
    </div>
  );
}

interface Previewed {
  readonly id: string;
  readonly revision: RevisionShown;
  readonly renderer: Renderer;
}

/** What a page adds under an open revision, such as a native file's words compared; or nothing. */
export type More = (revision: RevisionShown, before: number | null) => ReactNode;

/** A revision's preview: its content through its kind's renderer, read-only. */
function Preview({ id, revision, renderer }: Previewed) {
  return renderer.runs ? (
    <RunPreview id={id} revision={revision} renderer={renderer} />
  ) : (
    // Archived as far as a renderer knows, so nothing in it acts on the artifact.
    <ShownContext value={{ id, version: revision.version, archived: true }}>
      {renderer.preview?.(revision.data) ?? renderer.render(revision.data)}
    </ShownContext>
  );
}

/** What changed in a part: a source's lines, a title's or a text's words, under its name. */
function PartChanges({ part, changes }: Changed) {
  const named = useId();
  return (
    <section aria-labelledby={named} className="flex flex-col gap-1.5">
      <h4 id={named} className={cn(TYPE.labelQuiet, "first-letter:uppercase")}>
        {part.name}
      </h4>
      {part.diff === "lines" ? (
        <LineDiff changes={changes} name={part.name} />
      ) : (
        <Diff changes={changes} />
      )}
    </section>
  );
}

/** What changed, part by part, or that nothing in its content did. */
function Changes({ changed }: { changed: readonly Changed[] }) {
  if (changed.length === 0) {
    return (
      <p className={TYPE.meta}>Nothing in its content changed: it is as the version before.</p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {changed.map(({ part, changes }) => (
        <PartChanges key={part.name} part={part} changes={changes} />
      ))}
    </div>
  );
}

type Tab = "preview" | "source" | "changes";

const TAB =
  "-mb-px shrink-0 cursor-default whitespace-nowrap border-transparent border-b-2 px-3 py-1.5 font-medium text-muted text-sm -outline-offset-2 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus aria-selected:border-accent aria-selected:text-fg forced-colors:border-system-canvas forced-colors:aria-selected:border-system-highlight";

/** An open revision: its title and summary, where its kind has them, and its tabs. */
function Opened({
  id,
  revision,
  renderer,
  changed,
  more,
}: Previewed & { changed: readonly Changed[] | null; more: ReactNode }) {
  const runsHere = useRunsHere();
  const sources = partsOf(renderer, revision.data).filter(
    (part): part is RevisionPart & { language: string } => part.language !== undefined,
  );
  const tabs: [Tab, string][] = [
    ...(renderer.runs && !runsHere ? [] : [["preview", "Preview"] as [Tab, string]]),
    ...(sources.length > 0 ? [["source", "Source"] as [Tab, string]] : []),
    ...(changed === null ? [] : [["changes", "Changes"] as [Tab, string]]),
  ];
  // What changed first; for a first version, its source, as its content is shown above the list.
  const [tab, setTab] = useState<Tab>(
    changed !== null ? "changes" : sources.length > 0 ? "source" : (tabs[0]?.[0] ?? "preview"),
  );
  const title = renderer.about && renderer.title(revision.data);
  const about = renderer.about?.(revision.data);
  return (
    <div className="flex flex-col gap-3 border-line border-t px-4 pt-3 pb-4">
      {renderer.about && (
        <div className="flex flex-col gap-1">
          {title && <p className={TYPE.label}>{title}</p>}
          <p className="whitespace-pre-wrap text-fg text-sm">{about || "It has no summary."}</p>
        </div>
      )}
      <Tabs.Root value={tab} onValueChange={(chosen: Tab) => setTab(chosen)}>
        <Tabs.List
          aria-label={`Version ${revision.version}`}
          className="flex gap-1 overflow-x-auto border-line border-b"
        >
          {tabs.map(([value, label]) => (
            <Tabs.Tab key={value} value={value} className={TAB}>
              {label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        <Tabs.Panel value="preview" className="pt-3 outline-none">
          <Preview id={id} revision={revision} renderer={renderer} />
        </Tabs.Panel>
        <Tabs.Panel value="source" className="flex flex-col gap-3 pt-3 outline-none">
          {sources.map((part) => (
            <SourceView
              key={part.name}
              code={part.text}
              language={part.language}
              name={part.name}
            />
          ))}
        </Tabs.Panel>
        <Tabs.Panel value="changes" className="pt-3 outline-none">
          {changed !== null && <Changes changed={changed} />}
        </Tabs.Panel>
      </Tabs.Root>
      {more}
    </div>
  );
}

/** When a revision was made: how long ago, with the moment itself on hover. */
function When({ at, now }: { at: string; now: Date }) {
  const when = new Date(at);
  return (
    <time dateTime={at} title={when.toLocaleString()}>
      {ago(when, now)}
    </time>
  );
}

/** One revision: a disclosure, its summary the version, who and when, and what changed. */
function Revision({
  id,
  revision,
  renderer,
  changed,
  latest,
  more,
  now,
}: Previewed & {
  changed: readonly Changed[] | null;
  latest: boolean;
  more: ReactNode;
  now: Date;
}) {
  const [open, setOpen] = useState(latest);
  return (
    <li
      aria-label={`Version ${revision.version}`}
      className="rounded-lg border border-line bg-surface"
    >
      <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary className="flex cursor-pointer list-none items-start gap-2 rounded-lg px-4 py-3 outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden">
          <Icon
            icon={ChevronRight}
            className={cn(
              "mt-0.5 size-4 shrink-0 text-muted rtl:-scale-x-100",
              open && "rotate-90 rtl:rotate-90",
            )}
          />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className={TYPE.label}>Version {revision.version}</span>
              {latest && (
                <span className="rounded-sm border border-line px-1.5 text-muted text-xs">
                  Latest
                </span>
              )}
              <span className={TYPE.note}>
                by {revision.by}
                {revision.at && (
                  <>
                    {", "}
                    <When at={revision.at} now={now} />
                  </>
                )}
              </span>
            </span>
            <span className={cn(TYPE.meta, "break-words")}>{changedSaid(changed)}</span>
          </span>
        </summary>
        {open && (
          <Opened id={id} revision={revision} renderer={renderer} changed={changed} more={more} />
        )}
      </details>
    </li>
  );
}

/**
 * An artifact's revisions, newest first, whatever order they come in: the latest open, the rest
 * closed, each with what it changed since the one before. `compare` is `client`'s `changes`.
 */
export function Revisions({
  id,
  revisions,
  renderers,
  compare,
  more,
  now = new Date(),
}: {
  /** The artifact's id. */
  id: string;
  revisions: readonly RevisionShown[];
  renderers: Renderers;
  compare: Compare;
  more?: More;
  /** What "how long ago" is from: now, unless a test pins it. */
  now?: Date;
}): ReactNode {
  const [version, run] = useState<number | null>(null);
  const running = useMemo(() => ({ version, run }), [version]);
  // Worked out once each time the revisions are read, not on every render of the page.
  const shown = useMemo(() => {
    const ordered = [...revisions].sort((a, b) => a.version - b.version);
    return ordered
      .map((revision, at) => {
        const renderer = rendererFor(revision.kind, renderers);
        const before = ordered[at - 1] ?? null;
        return {
          revision,
          before: before?.version ?? null,
          renderer,
          changed: changedParts(renderer, revision.data, before?.data ?? null, compare),
        };
      })
      .reverse();
  }, [revisions, renderers, compare]);
  return (
    <RunningRevision value={running}>
      <ol aria-label="Revisions" className="flex flex-col gap-3">
        {shown.map(({ revision, before, renderer, changed }, at) => (
          <Revision
            key={revision.version}
            id={id}
            revision={revision}
            renderer={renderer}
            changed={changed}
            latest={at === 0}
            more={more?.(revision, before)}
            now={now}
          />
        ))}
      </ol>
    </RunningRevision>
  );
}
