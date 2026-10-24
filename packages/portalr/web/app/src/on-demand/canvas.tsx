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

/** The numbers an element is drawn by, each a finite number or left for Excalidraw to fill. */
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

/** An element's numbers and points as drawn: one that isn't finite is dropped, for restore to fill. */
function drawable(element: Record<string, unknown>): Record<string, unknown> {
  const kept: Record<string, unknown> = { ...element, link: null };
  for (const key of NUMBERS) {
    if (key in kept && !Number.isFinite(kept[key])) delete kept[key];
  }
  const points = kept.points;
  const pair = (point: unknown) =>
    Array.isArray(point) && point.length === 2 && point.every(Number.isFinite);
  if ("points" in kept && !(Array.isArray(points) && points.every(pair))) delete kept.points;
  return kept;
}

/**
 * A diagram's elements as the canvas takes them: objects only, none it doesn't draw, none with a
 * link, no number that isn't one, each restored by Excalidraw, which fills what one leaves out.
 */
export function elementsOf(data: Data): ExcalidrawElement[] {
  const held = data.elements;
  if (typeof held !== "object" || held === null || Array.isArray(held)) return [];
  const taken = Object.values(held)
    .filter(
      (element): element is Record<string, unknown> =>
        typeof element === "object" &&
        element !== null &&
        !Array.isArray(element) &&
        !UNDRAWN.has(String((element as { type?: unknown }).type)),
    )
    .map(drawable);
  const restored = (some: readonly Record<string, unknown>[]) =>
    restoreElements(some as unknown as ExcalidrawElement[], null).map((each) => ({
      ...each,
      link: null,
    }));
  try {
    // Together, so a label keeps its shape and an arrow what it binds.
    return restored(taken);
  } catch {
    // Excalidraw's restore throws on some it can't mend, such as an arrow with no points: then one
    // at a time, and each it can't is passed over, not the whole diagram.
    return taken.flatMap((element) => {
      try {
        return restored([element]);
      } catch {
        return [];
      }
    });
  }
}

/** Zoom by the keyboard, which view mode keeps: Ctrl or ⌘ with +, - or 0, and Shift+1 to fit. */
const ZOOM = new Set(["+", "=", "-", "_", "0"]);

/**
 * Keys the canvas may have: Tab and Escape, which the dialog keeps and closes by, arrows and
 * zoom. Any other, such as `?` for help, ⌘/ or ⌘K for the command palette, ⌘S or ⌘O, never reach
 * Excalidraw, nor the browser's own save or open.
 */
function kept(event: KeyboardEvent): boolean {
  if (event.key === "Tab" || event.key === "Escape" || event.key.startsWith("Arrow")) return true;
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
  const elements = useMemo(() => elementsOf(data), [data]);
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
