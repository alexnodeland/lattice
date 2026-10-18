/**
 * Choosing a file from the reader's computer: a file input, named by its label, which the keyboard
 * and every assistive technology reach, and around it a zone a file can be dropped on instead.
 * Dropping is the alternative, never the only way (portalr ADR-0049).
 */

import { FileUp } from "lucide-react";
import { type DragEvent, type ReactNode, useId, useState } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";

export function FileChooser({
  label,
  hint,
  accept,
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
  disabled?: boolean;
  /** Called with the file chosen or dropped: the first, if several are dropped. */
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
    const [file] = event.dataTransfer.files;
    if (file && !disabled) {
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
        "flex min-w-0 flex-col items-start gap-2 rounded-lg border-2 border-edge border-dashed bg-surface p-4 text-fg text-sm data-over:border-accent data-over:bg-wash forced-colors:data-over:border-system-highlight",
        disabled && "border-line text-muted",
        className,
      )}
    >
      <label htmlFor={input} className="flex items-center gap-2 font-semibold">
        <Icon icon={FileUp} />
        {label}
      </label>
      <input
        id={input}
        type="file"
        accept={accept}
        disabled={disabled}
        aria-describedby={described}
        // Cleared as the picker opens, so choosing the same file again is a change too, and the
        // input says what was chosen until then.
        onClick={(event) => {
          event.currentTarget.value = "";
        }}
        onChange={(event) => {
          const [file] = event.currentTarget.files ?? [];
          if (file) {
            onFile(file);
          }
        }}
        className="max-w-full text-muted text-sm outline-offset-2 file:mr-3 file:cursor-pointer file:rounded-md file:border file:border-edge file:border-solid file:bg-surface file:px-3 file:py-1.5 file:font-sans file:font-semibold file:text-fg file:text-sm focus-visible:outline-2 focus-visible:outline-focus disabled:file:cursor-not-allowed disabled:file:border-line disabled:file:bg-line disabled:file:text-muted"
      />
      <p id={described} className="text-muted">
        {hint}
        {hint && " "}Or drop it here.
      </p>
    </fieldset>
  );
}
