/**
 * An Excalidraw diagram, `excalidraw_diagram` (lattice RFC-0006, portalr ADR-0072): a card with its
 * name, how many elements it holds, and its description, the text alternative, which is also what
 * its revisions are compared by; and a way to open it on the canvas, which loads the canvas add-on
 * then, and only then. The card is drawn with what the routes that show artifacts already load, so
 * neither they nor the first load carry more for it.
 */

import {
  Button,
  capped,
  type Data,
  Disclosure,
  FailureAlert,
  Reading,
  type Renderer,
  retry,
  useLoaded,
} from "@portalr/ui";
import { useId, useMemo, useRef, useState } from "react";
import { describe } from "./diagram-text";

/** The canvas add-on, loaded the first time someone opens a canvas. */
const loadCanvas = () => import("./on-demand/canvas");

const nameOf = (data: Data) => (typeof data.name === "string" ? data.name : "");

/** The text alternative: what the agent reads of the diagram. */
const textOf = (data: Data) => describe(data.name, data.elements);

const live = (data: Data) => {
  const held = data.elements;
  if (typeof held !== "object" || held === null || Array.isArray(held)) return 0;
  return Object.values(held).filter(
    (element) =>
      typeof element === "object" &&
      element !== null &&
      !Array.isArray(element) &&
      !(element as { isDeleted?: unknown }).isDeleted,
  ).length;
};

/** The canvas, once its add-on has loaded; until then, or where it won't, why. */
function Opened({
  data,
  name,
  about,
  opener,
  onClose,
}: {
  data: Data;
  name: string;
  about: string;
  opener: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
}) {
  const { module: canvas, failed, error } = useLoaded(loadCanvas);
  if (failed) {
    return (
      <div className="flex flex-col items-start gap-2">
        <FailureAlert error={error} />
        <Button variant="secondary" size="sm" onClick={() => retry(loadCanvas)}>
          Try again
        </Button>
      </div>
    );
  }
  if (canvas === null) return <Reading>Loading the canvas…</Reading>;
  return (
    <canvas.CanvasDialog
      data={data}
      name={name}
      describedBy={about}
      finalFocus={opener}
      onClose={onClose}
    />
  );
}

function Card({ data }: { data: Data }) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const about = useId();
  const name = nameOf(data) || "Unnamed diagram";
  const count = live(data);
  const text = useMemo(() => textOf(data), [data]);
  return (
    <div className="flex flex-col gap-3">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-semibold text-fg text-sm">{name}</span>
        <span className="text-muted text-sm">
          Diagram · {count} {count === 1 ? "element" : "elements"}
        </span>
      </p>
      <Disclosure summary="Text version">
        {/* A diagram's words are anyone's in the workspace: text here, never markup. */}
        <pre id={about} className="whitespace-pre-wrap break-words text-fg text-xs">
          {text}
        </pre>
      </Disclosure>
      <div>
        <Button
          ref={opener}
          variant="secondary"
          size="sm"
          aria-describedby={about}
          onClick={() => setOpen(true)}
        >
          Open canvas
        </Button>
      </div>
      {open && (
        <Opened
          data={data}
          name={name}
          about={about}
          opener={opener}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

/**
 * The renderer for `excalidraw_diagram`: the card, titled by its name, its changes read from its
 * description, line by line.
 */
export const diagram: Renderer = {
  render: (data) => <Card data={data} />,
  text: textOf,
  parts: (data) => [{ name: "description", text: textOf(data), diff: "lines", language: "text" }],
  title: (data) => capped(nameOf(data)),
  diff: "lines",
  inline: true,
};
