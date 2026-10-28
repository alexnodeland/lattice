/**
 * A phone's composer footer (portalr ADR-0087), after the owner's model of a composer: a round
 * "+" at its start that opens an Add sheet (files, and the agent's mode with its choices), a pill
 * naming the model that opens a Select model sheet where the workspace offers more than one, and
 * the agent's mode said beside it when it isn't the default. Each sheet is the kit's dialog, a
 * sheet on a phone, named, keeping the focus, and giving it back to what opened it. It is the
 * thread page's alone, so it loads with that page, never with the first.
 */

import { type Api, type Artifactr, models, type OfferedModel } from "@portalr/client";
import { Button, Dialog, glyphs, Icon, IconButton, type Sent } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useRef, useState } from "react";
import { DEFAULT, remember } from "./model-memory";

type Mode = Artifactr.Thread["mode"];

/** The agent's modes, in words, each with what it means in one line. */
const MODES: readonly (readonly [Mode, string, string])[] = [
  ["edit", "Auto", "The assistant makes changes itself."],
  ["suggest", "Ask", "The assistant proposes changes for you to accept."],
];

/**
 * A model's one line: there is no description in the list the workspace offers, so it is said
 * from what is known of the model (generic, by its flags).
 */
const about = (model: OfferedModel) =>
  model.id === DEFAULT
    ? "The workspace's default"
    : model.reasoning
      ? "Thinks before it answers"
      : model.local
        ? "Runs on this deployment"
        : model.family || "A model the workspace allows";

const checked = <Icon icon={glyphs.check} className="text-accent" />;

/** A choice in a sheet: a full-width button, its name and line at its start, what it shows at its end. */
function Choice({
  name,
  meta,
  end,
  onClick,
  disabled,
  chosen,
}: {
  /** The one chosen among its set, said as pressed, and shown with a check. */
  chosen?: boolean;
  name: string;
  meta?: ReactNode;
  end?: ReactNode;
  onClick: () => void;
  disabled?: boolean | undefined;
}) {
  return (
    <Button
      variant="ghost"
      className="h-auto w-full justify-between whitespace-normal text-start"
      disabled={disabled}
      {...(chosen !== undefined && { "aria-pressed": chosen })}
      onClick={onClick}
    >
      <span className="flex min-w-0 flex-col">
        {name}
        {meta && <span className="font-normal text-muted text-xs">{meta}</span>}
      </span>
      {chosen ? checked : end}
    </Button>
  );
}

export function ComposerFooter({
  api,
  tenant,
  workspace,
  thread,
  focused,
  model,
  onModel,
  running,
  mode,
  onMode,
  onFiles,
}: {
  api: Api;
  tenant: string;
  workspace: string;
  thread: string;
  /** Whether the composer has had the focus: the models are read then, never as the page loads. */
  focused: boolean;
  /** The model the next message names, or null for the default. */
  model: string | null;
  onModel: (model: string | null) => void;
  /** A turn is running: the next message joins it, and keeps its model. */
  running: boolean;
  mode: Mode;
  /** Set the agent's mode, where the reader may; none leaves it said, not set. */
  onMode?: ((mode: Mode) => Sent) | undefined;
  /** Files chosen to add, for the page's uploader. */
  onFiles: (files: FileList) => void;
}) {
  const offered = useQuery({ ...models(api, tenant, workspace), enabled: focused }).data ?? [];
  const [adding, setAdding] = useState<"add" | "mode" | null>(null);
  const [choosing, setChoosing] = useState(false);
  const plus = useRef<HTMLButtonElement>(null);
  const pill = useRef<HTMLButtonElement>(null);
  const files = useRef<HTMLInputElement>(null);
  const current = offered.find((each) => each.id === (model ?? DEFAULT)) ?? offered[0];
  const said = MODES.find(([value]) => value === mode)?.[1] ?? mode;
  return (
    <span className="hidden min-w-0 items-center gap-2 phone:flex">
      <IconButton
        ref={plus}
        label="Add"
        icon={glyphs.plus}
        className="rounded-full"
        onClick={() => setAdding("add")}
      />
      <input
        ref={files}
        type="file"
        multiple
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
        onChange={(event) => {
          if (event.currentTarget.files?.length) {
            onFiles(event.currentTarget.files);
          }
        }}
      />
      {offered.length > 1 && current && (
        <Button
          ref={pill}
          variant="secondary"
          size="sm"
          // While a turn runs it is quiet, and still opens, to say why it can't be changed.
          className={running ? "min-w-0 rounded-full text-muted" : "min-w-0 rounded-full"}
          aria-label={`Model: ${current.label}`}
          aria-haspopup="dialog"
          onClick={() => setChoosing(true)}
        >
          <span className="truncate">{current.label}</span>
        </Button>
      )}
      {/* The mode said where it isn't the default, so a proposal never surprises. */}
      {mode === "suggest" && <span className="text-muted text-xs">{said}</span>}
      <Dialog
        open={adding !== null}
        onOpenChange={(open) => setAdding(open ? adding : null)}
        title={adding === "mode" ? "Agent mode" : "Add"}
        finalFocus={plus}
      >
        {adding === "mode" ? (
          <fieldset aria-label="Agent mode" className="m-0 flex flex-col border-0 p-0">
            {MODES.map(([value, word, line]) => (
              <Choice
                key={value}
                name={word}
                meta={line}
                chosen={value === mode}
                disabled={!onMode}
                onClick={() => {
                  void onMode?.(value);
                  setAdding(null);
                }}
              />
            ))}
          </fieldset>
        ) : (
          <div className="flex flex-col">
            <Choice
              name="Add files"
              onClick={() => {
                setAdding(null);
                files.current?.click();
              }}
            />
            <Choice
              name="Mode"
              end={
                <span className="flex items-center gap-1 text-muted text-sm">
                  {said}
                  <Icon icon={glyphs.chevronRight} />
                </span>
              }
              onClick={() => setAdding("mode")}
            />
          </div>
        )}
      </Dialog>
      <Dialog
        open={choosing}
        onOpenChange={setChoosing}
        title="Select model"
        {...(running && { description: "The running turn keeps its model" })}
        finalFocus={pill}
      >
        <fieldset aria-label="Models" className="m-0 flex flex-col border-0 p-0">
          {offered.map((each) => (
            <Choice
              key={each.id}
              name={each.label}
              meta={about(each)}
              chosen={each === current}
              disabled={running}
              onClick={() => {
                remember(thread, each.id);
                onModel(each.id === DEFAULT ? null : each.id);
                setChoosing(false);
              }}
            />
          ))}
        </fieldset>
      </Dialog>
    </span>
  );
}
