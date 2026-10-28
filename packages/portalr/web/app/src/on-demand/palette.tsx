/**
 * The workspace's palette (portalr ADR-0087), an add-on loaded the first time it is opened: one
 * field over what the workspace holds, its threads by title, its artifacts by title, its areas,
 * and starting a thread, each a way there. The field is a combobox over one list: the arrows move
 * through it, Enter follows the one shown chosen, Escape closes it, and the focus goes back to
 * the way it was opened from (`finalFocus`, the bar's magnifier).
 */

import type { Artifactr } from "@portalr/client";
import { type Glyph, glyphs, Icon, PaletteFrame, RunStatus } from "@portalr/ui";
import { type ReactNode, type RefObject, useId, useState } from "react";

/** One way on: what it says, its glyph, where it goes, and what is said at its end. */
interface Choice {
  readonly key: string;
  readonly group: string;
  readonly label: string;
  readonly icon: Glyph;
  readonly to: string;
  readonly hash?: string;
  readonly end?: ReactNode;
}

/** How many of each group a query shows, so the list stays one screen. */
const SHOWN = 6;

export function Palette({
  open,
  onOpenChange,
  finalFocus,
  workspace,
  state,
  titles,
  base,
  go,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  finalFocus: RefObject<HTMLElement | null>;
  workspace: string;
  /** The workspace as its stream holds it. */
  state: Artifactr.Workspace;
  /** The artifacts' titles, where they were read: an artifact without one is named by its id. */
  titles: ReadonlyMap<string, string>;
  /** The workspace's path, which each way on starts from. */
  base: string;
  /** Go to a path, at `hash` if given. */
  go: (to: string, hash?: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState(0);
  const list = useId();
  const words = query.trim().toLocaleLowerCase();
  const matches = (label: string) => label.toLocaleLowerCase().includes(words);
  // Each thread's turn that is going, or waits on someone, said beside it, as on the Threads page.
  const going = new Map(
    Object.values(state.runs)
      .filter((run) => run.status === "running" || run.status === "paused")
      .map((run) => [run.threadId, run.status] as const),
  );
  const choices: Choice[] = [
    ...Object.values(state.threads)
      .sort((a, b) => b.active - a.active)
      .map((thread) => ({ thread, label: thread.title || "Untitled" }))
      .filter(({ label }) => matches(label))
      .slice(0, SHOWN)
      .map(({ thread, label }) => {
        const status = going.get(thread.id);
        return {
          key: thread.id,
          group: "Threads",
          label,
          icon: glyphs.messageSquare,
          to: `${base}/threads/${encodeURIComponent(thread.id)}`,
          end: status && <RunStatus status={status} />,
        };
      }),
    ...Object.values(state.artifacts)
      .filter((artifact) => !artifact.archived)
      .sort((a, b) => b.seq - a.seq)
      .map((artifact) => ({ artifact, label: titles.get(artifact.id) ?? artifact.id }))
      .filter(({ label }) => matches(label))
      .slice(0, SHOWN)
      .map(({ artifact, label }) => ({
        key: artifact.id,
        group: "Artifacts",
        label,
        icon: glyphs.fileText,
        to: `${base}/artifacts/${encodeURIComponent(artifact.id)}`,
        end: <span className="text-muted text-xs tabular-nums">v{artifact.version}</span>,
      })),
    ...(
      [
        ["Threads", "", glyphs.messageSquare],
        ["Artifacts", "/artifacts", glyphs.fileText],
        ["Proposals", "/proposals", glyphs.workflow],
        ["Runs", "/runs", glyphs.play],
        ["Rules", "/rules", glyphs.zap],
      ] as const
    )
      .filter(([label]) => matches(label))
      .map(([label, path, icon]) => ({
        key: `go-${label}`,
        group: "Go to",
        label,
        icon,
        to: `${base}${path}`,
      })),
    ...(matches("New thread")
      ? [
          {
            key: "new",
            group: "Go to",
            label: "New thread",
            icon: glyphs.plus,
            to: base,
            hash: "new",
          },
        ]
      : []),
  ];
  const at = Math.min(chosen, choices.length - 1);
  const follow = (choice: Choice | undefined) => {
    if (choice) {
      onOpenChange(false);
      go(choice.to, choice.hash);
    }
  };
  const option = (index: number) => `${list}-${index}`;
  // The list in its groups, each choice keeping its place in the whole for the arrows.
  const groups = new Map<string, { choice: Choice; index: number }[]>();
  choices.forEach((choice, index) => {
    groups.set(choice.group, [...(groups.get(choice.group) ?? []), { choice, index }]);
  });
  return (
    <PaletteFrame
      open={open}
      title={`Search ${workspace}`}
      finalFocus={finalFocus}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          setQuery("");
          setChosen(0);
        }
      }}
    >
      <div className="flex items-center gap-2 border-line border-b px-4">
        <Icon icon={glyphs.search} className="text-muted" />
        <input
          role="combobox"
          aria-label="Search or go to"
          aria-expanded="true"
          aria-controls={list}
          aria-autocomplete="list"
          {...(choices.length > 0 && { "aria-activedescendant": option(at) })}
          placeholder="Search or go to…"
          value={query}
          onChange={(event) => {
            setQuery(event.currentTarget.value);
            setChosen(0);
          }}
          onKeyDown={(event) => {
            const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
            if (step !== undefined && choices.length > 0) {
              event.preventDefault();
              setChosen((at + step + choices.length) % choices.length);
            } else if (event.key === "Enter") {
              event.preventDefault();
              follow(choices[at]);
            }
          }}
          className="h-12 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted"
        />
        <kbd className="rounded-(--radius-2) border border-line px-1.5 text-muted text-xs">Esc</kbd>
      </div>
      <div id={list} role="listbox" aria-label="Results" className="overflow-y-auto p-1.5">
        {choices.length === 0 && <p className="px-2.5 py-2 text-muted text-sm">Nothing matches.</p>}
        {[...groups].map(([group, members]) => (
          <fieldset key={group} aria-labelledby={`${list}-${group}`} className="m-0 border-0 p-0">
            <div id={`${list}-${group}`} className="px-2.5 pt-2 pb-1 text-muted text-xs">
              {group}
            </div>
            {members.map(({ choice, index }) => (
              <div
                key={choice.key}
                id={option(index)}
                role="option"
                aria-selected={index === at}
                tabIndex={-1}
                onPointerMove={() => setChosen(index)}
                // The field keeps the focus as a pointer presses; a click, a tap, or a screen
                // reader's or Voice Control's activation follows the choice.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => follow(choice)}
                onKeyDown={(event) => event.key === "Enter" && follow(choice)}
                className="flex cursor-default items-center gap-2.5 rounded-(--radius-3) px-2.5 py-2 text-sm aria-selected:bg-subtle"
              >
                <Icon icon={choice.icon} className="text-muted" />
                <span className="min-w-0 flex-1 truncate">{choice.label}</span>
                {choice.end}
              </div>
            ))}
          </fieldset>
        ))}
      </div>
    </PaletteFrame>
  );
}
