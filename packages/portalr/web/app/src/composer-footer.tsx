/**
 * A phone's composer footer (portalr ADR-0087), after the owner's model of a composer: a round
 * "+" at its start that opens an Add sheet (files, and the agent's mode with its choices), a pill
 * naming the model that opens a Select model sheet where the workspace offers more than one, and
 * the agent's mode said beside it when it isn't the default. Each sheet is the kit's dialog, a
 * sheet on a phone, named, keeping the focus, and giving it back to what opened it. It is the
 * thread page's alone, so it loads with that page, never with the first.
 */

import { type Api, type Artifactr, models, type OfferedModel } from "@portalr/client";
import { Button, ChoiceList, Dialog, glyphs, Icon, IconButton, type Sent } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { DEFAULT, remember } from "./model-memory";

type Mode = Artifactr.Thread["mode"];

/** The agent's modes, each with what it means in one line. */
const MODES = [
  { value: "edit", label: "Auto", line: "The assistant makes changes itself." },
  { value: "suggest", label: "Ask", line: "The assistant proposes changes for you to accept." },
] as const satisfies readonly { value: Mode; label: string; line: string }[];

/**
 * A model's line: the list the workspace offers carries no description, so only what is known
 * for sure is said, a fixed line for the default, the fast model and one that thinks first, and
 * nothing for any other: its name alone.
 */
const about = (model: OfferedModel) =>
  model.id === DEFAULT
    ? "The workspace's default"
    : model.id === "fast"
      ? "Small and quick"
      : model.reasoning
        ? "Thinks before it answers"
        : undefined;

/** A row of the Add sheet: a full-width button, its name at its start, what it shows at its end. */
const row = "h-auto w-full justify-between whitespace-normal text-start";

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
  const back = useRef<HTMLButtonElement>(null);
  const modeRow = useRef<HTMLButtonElement>(null);
  const current = offered.find((each) => each.id === (model ?? DEFAULT)) ?? offered[0];
  const said = MODES.find((each) => each.value === mode)?.label ?? mode;
  // Into Mode, the focus goes to Back; out of it, to the Mode row it came from.
  const [moved, setMoved] = useState(false);
  useEffect(() => {
    if (moved) {
      (adding === "mode" ? back : modeRow).current?.focus();
    }
  }, [adding, moved]);
  const view = (next: "add" | "mode") => {
    setMoved(true);
    setAdding(next);
  };
  // Escape in Mode goes back to Add first; in Add it closes the sheet, as the dialog does.
  const backOnEscape = (event: KeyboardEvent) => {
    if (event.key === "Escape" && adding === "mode") {
      event.preventDefault();
      event.stopPropagation();
      view("add");
    }
  };
  return (
    <span className="hidden min-w-0 items-center gap-2 phone:flex">
      <IconButton
        ref={plus}
        label="Add"
        icon={glyphs.plus}
        className="rounded-full"
        onClick={() => {
          setMoved(false);
          setAdding("add");
        }}
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
      {/* The mode said where it isn't the default, as a mode, so a proposal never surprises. */}
      {mode === "suggest" && <span className="text-muted text-xs">Mode: {said}</span>}
      <Dialog
        open={adding !== null}
        onOpenChange={(open) => setAdding(open ? adding : null)}
        title={adding === "mode" ? "Agent mode" : "Add"}
        finalFocus={plus}
      >
        {/* A wrapper that hears Escape before the dialog does, so Mode goes back first. */}
        <div onKeyDownCapture={backOnEscape} className="flex flex-col gap-1">
          {adding === "mode" ? (
            <>
              <Button
                ref={back}
                variant="ghost"
                size="sm"
                className="self-start"
                onClick={() => view("add")}
              >
                <Icon icon={glyphs.chevronLeft} />
                Back to Add
              </Button>
              <ChoiceList
                label="Agent mode"
                value={mode}
                options={MODES}
                disabled={!onMode}
                onChange={(value) => void onMode?.(value)}
              />
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                className={row}
                onClick={() => {
                  setAdding(null);
                  // After the sheet has given the focus back, the system's file chooser.
                  requestAnimationFrame(() => files.current?.click());
                }}
              >
                Add files
              </Button>
              <Button ref={modeRow} variant="ghost" className={row} onClick={() => view("mode")}>
                Mode
                <span className="flex items-center gap-1 font-normal text-muted text-sm">
                  {said}
                  <Icon icon={glyphs.chevronRight} />
                </span>
              </Button>
            </>
          )}
        </div>
      </Dialog>
      <Dialog
        open={choosing}
        onOpenChange={setChoosing}
        title="Select model"
        {...(running && { description: "Fixed for this turn" })}
        finalFocus={pill}
      >
        <ChoiceList
          label="Models"
          value={current?.id ?? DEFAULT}
          options={offered.map((each) => ({
            value: each.id,
            label: each.label,
            line: about(each),
          }))}
          disabled={running}
          onChange={(value) => {
            remember(thread, value);
            onModel(value === DEFAULT ? null : value);
          }}
        />
      </Dialog>
    </span>
  );
}
