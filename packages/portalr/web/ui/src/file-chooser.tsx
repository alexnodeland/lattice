/**
 * Choosing a file from the reader's computer: a file input, named by its label, which the keyboard
 * and every assistive technology reach, and around it a zone a file can be dropped on instead.
 * Dropping is the alternative, never the only way (portalr ADR-0049).
 */

import { type DragEvent, type ReactNode, useId, useState } from "react";
import { buttonLook } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";
import { glyphs } from "./icons";

export function FileChooser({
  label,
  hint,
  accept,
  multiple = false,
  disabled = false,
  onFile,
  className,
}: {
  /** What the file is, such as "The edited file". */
  label: string;
  /** What to choose, and where it came from. */
  hint?: ReactNode;
  /** The types the input offers, such as `.docx`; a dropped file of another is still given. */
  accept?: string | undefined;
  /** Whether several files may be chosen or dropped at once. */
  multiple?: boolean;
  disabled?: boolean;
  /**
   * Called with the file chosen or dropped: the first, if several are dropped; or, `multiple`,
   * with each in turn.
   */
  onFile: (file: File) => void;
  className?: string;
}) {
  const input = useId();
  const described = useId();
  // How deep a drag is inside the zone: entering a child enters before the zone is left, so the
  // zone is marked from the first enter until the last leave, without flickering in between.
  const [depth, setDepth] = useState(0);
  const over = depth > 0 && !disabled;
  const dragging = (event: DragEvent, by: number) => {
    event.preventDefault();
    setDepth((now) => Math.max(0, now + by));
  };
  const dropped = (event: DragEvent) => {
    event.preventDefault();
    setDepth(0);
    if (!disabled) {
      given(event.dataTransfer.files);
    }
  };
  const given = (files: FileList | null) => {
    for (const file of Array.from(files ?? []).slice(0, multiple ? undefined : 1)) {
      onFile(file);
    }
  };
  return (
    // A group of the input, the way to choose, and the zone around it, where dropping is the
    // alternative; named by nothing, since its input already says what it is.
    <fieldset
      onDragEnter={(event) => dragging(event, 1)}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => dragging(event, -1)}
      onDrop={dropped}
      data-over={over || undefined}
      className={cn(
        "flex min-w-0 flex-col items-start gap-2 rounded-(--card-radius) border border-edge border-dashed bg-surface p-(--card-pad) text-fg text-sm data-over:border-accent data-over:bg-wash forced-colors:data-over:border-system-highlight",
        disabled && "border-line text-muted",
        className,
      )}
    >
      <label htmlFor={input} className="flex items-center gap-2 font-semibold">
        <Icon icon={glyphs.fileUp} />
        {label}
      </label>
      {/*
       * The input itself is out of sight, so the browser's own button and its "No file chosen"
       * aren't drawn: the keyboard and assistive technology still reach it, named by its label
       * and by the kit button beside it, its second label, which shows its focus and opens it on
       * a click (portalr ADR-0049).
       */}
      <span className="flex items-center">
        <input
          id={input}
          type="file"
          accept={accept}
          multiple={multiple}
          disabled={disabled}
          aria-describedby={described}
          // Cleared as the picker opens, so choosing the same file again is a change too, and the
          // input says what was chosen until then.
          onClick={(event) => {
            event.currentTarget.value = "";
          }}
          onChange={(event) => given(event.currentTarget.files)}
          className="peer sr-only"
        />
        <label
          htmlFor={input}
          // So the button's own disabled look holds, its hover and press with it.
          data-disabled={disabled || undefined}
          className={cn(
            buttonLook("secondary", "sm"),
            "cursor-pointer peer-focus-visible:outline-(length:--focus-width) peer-focus-visible:outline-focus",
          )}
        >
          {multiple ? "Choose files" : "Choose a file"}
        </label>
      </span>
      <p id={described} className="text-muted">
        {hint}
        {hint && " "}Or drop {multiple ? "them" : "it"} here.
      </p>
    </fieldset>
  );
}
