/**
 * An artifact's revisions, readable (portalr ADR-0054): newest first, each a disclosure whose
 * summary says which version it is, who made it, when, and what it changed, the latest open and
 * the rest closed. Open, a revision shows its kind's title and summary where it has them, then
 * its Preview, its Source and its Changes, as tabs: its content through its kind's renderer, its
 * sources numbered and highlighted, and what changed since the previous kept version, part by
 * part, a
 * source's line by line and a title's word by word. A kind whose preview runs what it holds, a mini
 * app, runs one revision at a time, when asked, and only where apps run; what is done in a preview
 * is not saved.
 */

import { Tabs } from "@base-ui/react/tabs";
import type { Change, Granularity } from "@portalr/client/diff";
import { createContext, type ReactNode, use, useEffect, useId, useMemo, useState } from "react";
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
import { Badge } from "./badge";
import { Button } from "./button";
import { cn } from "./cn";
import { Disclosure } from "./disclosure";
import { Heading } from "./heading";
import { Icon } from "./icon";
import { glyphs } from "./icons";
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

/** A part that changed since the previous kept version, and how. */
interface Changed {
  readonly part: RevisionPart;
  readonly changes: Change[] | null;
}

/** A revision beside the one before it: each read through its own kind's renderer. */
interface Pair {
  readonly renderer: Renderer;
  readonly data: Data;
  readonly before: { readonly renderer: Renderer; readonly data: Data } | null;
}

/**
 * The parts that changed since the previous kept version, cheaply, by their text alone: a part it
 * has, or
 * one the version before had and it hasn't, which is removed. Null for a first version.
 */
function changedNames(pair: Pair): RevisionPart[] | null {
  const { renderer, data, before } = pair;
  if (before === null) {
    return null;
  }
  const was = new Map(partsOf(before.renderer, before.data).map((part) => [part.name, part]));
  const now = partsOf(renderer, data);
  const kept = new Set(now.map((part) => part.name));
  return [
    ...now.filter((part) => (was.get(part.name)?.text ?? "") !== part.text),
    ...[...was.values()]
      .filter((part) => !kept.has(part.name))
      .map((part) => ({ ...part, text: "" })),
  ];
}

/** Each pair's changes, kept by its data's identity, so a revision read again isn't compared again. */
const compared = new WeakMap<Compare, WeakMap<Data, WeakMap<Data, Changed[]>>>();

/** What a revision changed, part by part, since the previous kept version, or null for the first. */
function changedParts(pair: Pair, compare: Compare): Changed[] | null {
  const parts = changedNames(pair);
  if (parts === null || pair.before === null) {
    return null;
  }
  const byCompare = compared.get(compare) ?? new WeakMap();
  compared.set(compare, byCompare);
  const byAfter = byCompare.get(pair.data) ?? new WeakMap();
  byCompare.set(pair.data, byAfter);
  const found = byAfter.get(pair.before.data);
  if (found) {
    return found;
  }
  const was = new Map(
    partsOf(pair.before.renderer, pair.before.data).map((part) => [part.name, part.text]),
  );
  const changed = parts.map((part) => ({
    part,
    changes: compare(was.get(part.name) ?? "", part.text, part.diff),
  }));
  byAfter.set(pair.before.data, changed);
  return changed;
}

/**
 * What a revision changed, in a line: "First version", "Changed the title and the HTML (+3 −1)".
 * Parts alone, without what changed in each, are named without their counts.
 */
export function changedSaid(
  changed:
    | readonly (Changed | { readonly part: RevisionPart; readonly changes?: undefined })[]
    | null,
): string {
  if (changed === null) {
    return "First version";
  }
  if (changed.length === 0) {
    return "No change to its content";
  }
  const each = changed.map(({ part, changes }) => {
    if (part.diff === "words" || changes == null) {
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
  readonly run: (next: (now: number | null) => number | null) => void;
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

interface Previewed {
  readonly id: string;
  readonly revision: RevisionShown;
  readonly renderer: Renderer;
}

/** A revision's preview of a kind that runs what it holds: run on asking, one at a time. */
function RunPreview({ id, revision, renderer, runs }: Previewed & { runs: boolean }) {
  const host = use(AppHostContext);
  const running = use(RunningRevision);
  const preview = useMemo(() => host && previewHost(host), [host]);
  // Where it may no longer run, archived or with apps switched off, nothing of it is drawn.
  const live = runs && running.version === revision.version;
  // Closed, or another tab chosen, a preview stops: reopened, it waits to be asked again.
  const { run } = running;
  const { version } = revision;
  useEffect(() => {
    if (!runs) {
      run((now) => (now === version ? null : now));
    }
    return () => run((now) => (now === version ? null : now));
  }, [run, version, runs]);
  if (!runs) {
    return null;
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => running.run(() => (live ? null : revision.version))}
        >
          <Icon icon={live ? glyphs.square : glyphs.play} className="size-3.5" />
          {live ? `Stop version ${revision.version}` : `Run version ${revision.version}`}
        </Button>
        <p className={TYPE.note}>
          One version runs at a time. What you do in a preview isn't saved, and it sends nothing; a
          link it opens is still asked about first.
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

/** What a page adds under an open revision, such as a native file's words compared; or nothing. */
export type More = (revision: RevisionShown, before: number | null) => ReactNode;

/** Each open revision's tab panel: its focus ring drawn inside, as a tab's is. */
const PANEL =
  "rounded-sm pt-3 -outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus";

/** A revision's preview: its content through its kind's renderer, read-only. */
function Preview({ id, revision, renderer, runs }: Previewed & { runs: boolean }) {
  return renderer.runs ? (
    <RunPreview id={id} revision={revision} renderer={renderer} runs={runs} />
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
      <Heading id={named} level={4} look="labelQuiet" className="first-letter:uppercase">
        {part.name}
      </Heading>
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
  "-mb-px shrink-0 cursor-default whitespace-nowrap border-transparent border-b-2 px-3 py-1.5 font-medium text-muted text-sm -outline-offset-(--focus-offset) hover:text-fg focus-visible:outline-(length:--focus-width) focus-visible:outline-focus aria-selected:border-accent aria-selected:text-fg forced-colors:border-system-canvas forced-colors:aria-selected:border-system-highlight";

/** An open revision: its title and summary, where its kind has them, and its tabs. */
function Opened({
  id,
  revision,
  renderer,
  pair,
  compare,
  archived,
  more,
}: Previewed & { pair: Pair; compare: Compare; archived: boolean; more: ReactNode }) {
  const runsHere = useRunsHere() && !archived;
  // Compared only once open, and kept: closing and opening it again compares nothing again.
  const changed = useMemo(() => changedParts(pair, compare), [pair, compare]);
  const sources = partsOf(renderer, revision.data).filter(
    (part): part is RevisionPart & { language: string } => part.language !== undefined,
  );
  const tabs: [Tab, string][] = [
    ...(renderer.runs && !runsHere ? [] : [["preview", "Preview"] as [Tab, string]]),
    ...(sources.length > 0 ? [["source", "Source"] as [Tab, string]] : []),
    ...(changed === null ? [] : [["changes", "Changes"] as [Tab, string]]),
  ];
  // What changed first; for a first version, its source, as its content is shown above the list.
  const first: Tab =
    changed !== null ? "changes" : sources.length > 0 ? "source" : (tabs[0]?.[0] ?? "preview");
  const [chosen, setTab] = useState<Tab>(first);
  // A tab that goes, as Preview does when the app is archived or apps are switched off while it
  // is open, gives way to the first: its panel, and a preview running in it, stop.
  const tab = tabs.some(([value]) => value === chosen) ? chosen : first;
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
        <Tabs.Panel value="preview" className={PANEL}>
          <Preview id={id} revision={revision} renderer={renderer} runs={runsHere} />
        </Tabs.Panel>
        <Tabs.Panel value="source" className={cn(PANEL, "flex flex-col gap-3")}>
          {sources.map((part) => (
            <SourceView
              key={part.name}
              code={part.text}
              language={part.language}
              name={part.name}
            />
          ))}
        </Tabs.Panel>
        <Tabs.Panel value="changes" className={PANEL}>
          {changed !== null && <Changes changed={changed} />}
        </Tabs.Panel>
      </Tabs.Root>
      {more}
    </div>
  );
}

/**
 * When a revision was made: how long ago, a moment a clock ahead of the page's said as "just now",
 * and the moment itself, read by a screen reader and shown on hover.
 */
function When({ at, now }: { at: string; now: Date }) {
  const when = new Date(at);
  const moment = when.toLocaleString();
  return (
    <time dateTime={at} title={moment}>
      {when > now ? "just now" : ago(when, now)}
      <span className="sr-only"> ({moment})</span>
    </time>
  );
}

/** One revision: a disclosure, its summary the version, who and when, and what changed. */
function Revision({
  id,
  revision,
  renderer,
  pair,
  compare,
  archived,
  latest,
  open,
  onOpenChange,
  more,
  now,
}: Previewed & {
  pair: Pair;
  compare: Compare;
  archived: boolean;
  latest: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  more: () => ReactNode;
  now: Date;
}) {
  // Closed, a revision says which parts changed; their counts are worked out once it is open.
  const names = useMemo(() => changedNames(pair), [pair]);
  const counted = useMemo(() => (open ? changedParts(pair, compare) : null), [open, pair, compare]);
  return (
    <li
      aria-label={`Version ${revision.version}`}
      className="rounded-(--card-radius) border border-line bg-surface"
    >
      <Disclosure
        look="block"
        open={open}
        onOpenChange={onOpenChange}
        triggerClassName="rounded-(--card-radius) px-4 py-3"
        panelClassName="data-open:pt-0"
        summary={
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className={TYPE.label}>Version {revision.version}</span>
              {latest && <Badge>Latest</Badge>}
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
            <span className={cn(TYPE.meta, "break-words")}>
              {changedSaid(counted ?? names?.map((part) => ({ part })) ?? null)}
            </span>
          </span>
        }
      >
        {open && (
          <Opened
            id={id}
            revision={revision}
            renderer={renderer}
            pair={pair}
            compare={compare}
            archived={archived}
            more={more()}
          />
        )}
      </Disclosure>
    </li>
  );
}

/**
 * An artifact's revisions, newest first, whatever order they come in: the latest open, the rest
 * closed, each with what it changed since the previous kept version. `compare` is `client`'s
 * `changes`.
 */
export function Revisions({
  id,
  revisions,
  renderers,
  compare,
  more,
  archived = false,
  now = new Date(),
}: {
  /** The artifact's id. */
  id: string;
  /** Whether it is archived, which switches an app off: then no revision of it runs. */
  archived?: boolean;
  revisions: readonly RevisionShown[];
  renderers: Renderers;
  compare: Compare;
  more?: More;
  /** What "how long ago" is from: now, unless a test pins it. */
  now?: Date;
}): ReactNode {
  const [version, run] = useState<number | null>(null);
  const running = useMemo(() => ({ version, run }), [version]);
  // One revision open at a time (portalr ADR-0080): the latest as the list is first shown, and
  // a newer one as it arrives; opening another closes it.
  const latest = revisions.reduce((most, revision) => Math.max(most, revision.version), 0);
  const [opened, setOpened] = useState({ latest, version: latest as number | null });
  if (opened.latest !== latest) {
    setOpened({ latest, version: latest });
  }
  // Each revision beside the one before; what changed is worked out as each is shown or opened.
  const shown = useMemo(() => {
    const ordered = [...revisions].sort((a, b) => a.version - b.version);
    return ordered
      .map((revision, at) => {
        const renderer = rendererFor(revision.kind, renderers);
        const before = ordered[at - 1] ?? null;
        const pair: Pair = {
          renderer,
          data: revision.data,
          before: before && { renderer: rendererFor(before.kind, renderers), data: before.data },
        };
        return { revision, before: before?.version ?? null, renderer, pair };
      })
      .reverse();
  }, [revisions, renderers]);
  return (
    <RunningRevision value={running}>
      <ol aria-label="Revisions" className="flex flex-col gap-3">
        {shown.map(({ revision, before, renderer, pair }) => (
          <Revision
            key={revision.version}
            id={id}
            revision={revision}
            renderer={renderer}
            pair={pair}
            compare={compare}
            archived={archived}
            latest={revision.version === latest}
            open={revision.version === opened.version}
            onOpenChange={(open) => setOpened({ latest, version: open ? revision.version : null })}
            more={() => more?.(revision, before)}
            now={now}
          />
        ))}
      </ol>
    </RunningRevision>
  );
}
