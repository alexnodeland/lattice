/**
 * The canvas add-on (portalr ADR-0072): Excalidraw, which draws a diagram in full, in a chunk of
 * its own, loaded only when someone opens a diagram's canvas. In this phase it shows the diagram,
 * to look at, pan and zoom: drawing on it, and the images it holds, come with editing.
 *
 * A diagram's elements are anyone's in the workspace to write, so the canvas takes only what it
 * draws: no link, no embedded page and no image, each element restored by Excalidraw as its own
 * canvas restores one, and a diagram it can't draw falls back to its text version. What would
 * leave view mode is refused at the canvas's edge: its shortcuts, a drop, a paste, its menus.
 */

import "@excalidraw/excalidraw/index.css";
import "./canvas.css";
import { Excalidraw, restoreElements } from "@excalidraw/excalidraw";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import { type Data, FailureAlert, WholeDialog } from "@portalr/ui";
import {
  Component,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
  type SyntheticEvent,
  useMemo,
  useSyncExternalStore,
} from "react";

declare global {
  interface Window {
    EXCALIDRAW_ASSET_PATH: string;
  }
}

// The faces are the app's own copy (excalidraw.ts), never a CDN's. Set as the add-on loads, after
// Excalidraw's module has run: it reads the path only as it loads a face, so it is in time.
window.EXCALIDRAW_ASSET_PATH = `${import.meta.env.BASE_URL}excalidraw/`;

/** The page's scheme, as ui's tokens follow it: a chosen one, or the system's. */
function scheme(): "light" | "dark" {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function watchScheme(changed: () => void): () => void {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const observer = new MutationObserver(changed);
  observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });
  media.addEventListener("change", changed);
  return () => {
    observer.disconnect();
    media.removeEventListener("change", changed);
  };
}

/** What the canvas never draws in this phase: a page embedded, or an image, which load from away. */
const UNDRAWN = new Set(["embeddable", "iframe", "image"]);

/** The numbers an element is drawn by, each finite and within reach, or left for restore to fill. */
const NUMBERS = [
  "x",
  "y",
  "width",
  "height",
  "angle",
  "fontSize",
  "strokeWidth",
  "opacity",
  "roughness",
];

/** How far from the origin a number the canvas draws by may be: further, and it is left out. */
const REACH = 1e9;

/** Lists an element holds, each a list or left for restore to fill. */
const LISTS = ["groupIds", "boundElements"];

/** Colours an element holds, each a string or left for restore to fill. */
const COLOURS = ["strokeColor", "backgroundColor"];

const finite = (value: unknown) => typeof value === "number" && Math.abs(value) <= REACH;

/** An element's numbers, lists, colours and points as drawn: one that isn't is dropped, for restore to fill. */
function drawable(element: Record<string, unknown>): Record<string, unknown> {
  const kept: Record<string, unknown> = { ...element, link: null };
  for (const key of NUMBERS) {
    if (key in kept && !finite(kept[key])) delete kept[key];
  }
  for (const key of LISTS) {
    if (key in kept && !Array.isArray(kept[key])) delete kept[key];
  }
  for (const key of COLOURS) {
    if (key in kept && typeof kept[key] !== "string") delete kept[key];
  }
  const points = kept.points;
  const pair = (point: unknown) =>
    Array.isArray(point) && point.length === 2 && point.every(finite);
  if ("points" in kept && !(Array.isArray(points) && points.every(pair))) delete kept.points;
  return kept;
}

/** What the canvas draws of a diagram, and how many of its live elements it leaves out. */
export interface Taken {
  readonly elements: ExcalidrawElement[];
  readonly left: number;
}

const isElement = (element: unknown): element is Record<string, unknown> =>
  typeof element === "object" && element !== null && !Array.isArray(element);

/**
 * A diagram's elements as the canvas takes them: objects only, none it doesn't draw, none with a
 * link, nothing it would draw by that isn't what it should be, each restored by Excalidraw, which
 * fills what one leaves out; and how many of the live ones are left out, which the canvas says.
 */
export function elementsOf(data: Data): Taken {
  const held = data.elements;
  if (!isElement(held)) return { elements: [], left: 0 };
  const objects = Object.values(held).filter(isElement);
  const live = objects.filter((element) => !element.isDeleted).length;
  const taken = objects.filter((element) => !UNDRAWN.has(String(element.type))).map(drawable);
  const restored = (some: readonly Record<string, unknown>[]) =>
    restoreElements(some as unknown as ExcalidrawElement[], null).map((each) => ({
      ...each,
      link: null,
    }));
  let elements: ExcalidrawElement[];
  try {
    // Together, so a label keeps its shape and an arrow what it binds.
    elements = restored(taken);
  } catch {
    // Excalidraw's restore throws on some it can't mend, such as an arrow with no points: then one
    // at a time, and each it can't is left out, not the whole diagram.
    elements = taken.flatMap((element) => {
      try {
        return restored([element]);
      } catch {
        return [];
      }
    });
  }
  const kept = new Set(elements.map((element) => element.id));
  const here = (binding: { elementId?: unknown } | null | undefined) =>
    binding && typeof binding.elementId === "string" && kept.has(binding.elementId)
      ? binding
      : null;
  // What an element binds to, or is held in, is let go where that isn't drawn.
  const bound = elements.map((element) => {
    const fields = element as unknown as Record<string, unknown>;
    const changed: Record<string, unknown> = {
      ...fields,
      boundElements: Array.isArray(fields.boundElements)
        ? fields.boundElements.filter((each: { id?: unknown }) => kept.has(String(each?.id)))
        : fields.boundElements,
    };
    if ("startBinding" in fields) changed.startBinding = here(fields.startBinding as never);
    if ("endBinding" in fields) changed.endBinding = here(fields.endBinding as never);
    if (typeof fields.containerId === "string" && !kept.has(fields.containerId)) {
      changed.containerId = null;
    }
    return changed as unknown as ExcalidrawElement;
  });
  return { elements: bound, left: live - bound.filter((element) => !element.isDeleted).length };
}

/** Zoom by the keyboard, which view mode keeps: Ctrl or ⌘ with +, - or 0. */
const ZOOM = new Set(["+", "=", "-", "_", "0"]);

/**
 * Keys the canvas may have: Tab and Escape, which the dialog keeps and closes by; the arrows;
 * Ctrl or ⌘ with +, - or 0, which zoom; the modifiers alone; and Enter and Space on a button, such
 * as its zoom buttons, unmodified. Any other, such as `?` for help, ⌘/ or ⌘K for the command
 * palette, ⌘S or ⌘O, never reaches Excalidraw, nor the browser's own save or open.
 */
export function kept(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "target">,
): boolean {
  if (event.key === "Tab" || event.key === "Escape" || event.key.startsWith("Arrow")) return true;
  const onButton =
    event.target instanceof Element && event.target.closest("button, [role=button]") !== null;
  if ((event.key === "Enter" || event.key === " ") && onButton) {
    return !event.ctrlKey && !event.metaKey && !event.altKey;
  }
  if (
    event.key === "Shift" ||
    event.key === "Control" ||
    event.key === "Meta" ||
    event.key === "Alt"
  ) {
    return true;
  }
  return (event.ctrlKey || event.metaKey) && !event.altKey && ZOOM.has(event.key);
}

const refused = (event: SyntheticEvent) => {
  event.preventDefault();
  event.stopPropagation();
};

/** A diagram the canvas couldn't draw: why, and that its text version holds it. */
class Drawn extends Component<{ children: ReactNode }, { error: unknown }> {
  override state: { error: unknown } = { error: null };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  override render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div className="flex flex-col items-start gap-2 p-4">
        <FailureAlert error={this.state.error} />
        <p className="text-muted text-sm">
          The canvas couldn't draw it: its text version holds it.
        </p>
      </div>
    );
  }
}

function Canvas({ data, describedBy }: { data: Data; describedBy: string }) {
  const theme = useSyncExternalStore(watchScheme, scheme);
  const { elements, left } = useMemo(() => elementsOf(data), [data]);
  return (
    <section
      className="absolute inset-0"
      aria-label="Canvas"
      aria-describedby={describedBy}
      onKeyDownCapture={(event) => kept(event) || refused(event)}
      onKeyUpCapture={(event) => kept(event) || refused(event)}
      onDragOverCapture={refused}
      onDropCapture={refused}
      onPasteCapture={refused}
      onContextMenuCapture={refused}
    >
      {left > 0 && (
        <p
          role="status"
          className="absolute top-2 right-2 z-10 rounded-(--input-radius) bg-surface px-2 py-1 text-muted text-xs"
        >
          {left} {left === 1 ? "element" : "elements"} not drawn here: its text version lists all
        </p>
      )}
      <Excalidraw
        initialData={{ elements, scrollToContent: true }}
        viewModeEnabled
        zenModeEnabled
        langCode="en"
        theme={theme}
        detectScroll={false}
        handleKeyboardGlobally={false}
        validateEmbeddable={false}
        onLinkOpen={(_, event) => event.preventDefault()}
        UIOptions={{
          canvasActions: {
            changeViewBackgroundColor: false,
            clearCanvas: false,
            export: false,
            loadScene: false,
            saveAsImage: false,
            saveToActiveFile: false,
            toggleTheme: false,
          },
          tools: { image: false },
        }}
      />
    </section>
  );
}

/**
 * The canvas over the page, in a dialog that fills the window, open from when it loads until it is
 * closed; focus goes back to `finalFocus`, the button that opened it.
 */
export function CanvasDialog({
  data,
  name,
  describedBy,
  finalFocus,
  onClose,
}: {
  data: Data;
  name: string;
  describedBy: string;
  finalFocus: RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  return (
    <WholeDialog
      open
      onOpenChange={(open) => open || onClose()}
      title={name}
      close="Close canvas"
      describedBy={describedBy}
      finalFocus={finalFocus}
    >
      <Drawn>
        <Canvas data={data} describedBy={describedBy} />
      </Drawn>
    </WholeDialog>
  );
}
