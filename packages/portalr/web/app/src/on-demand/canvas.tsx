/**
 * The canvas add-on (portalr ADR-0072): Excalidraw, which draws a diagram in full, in a chunk of
 * its own, loaded only when someone opens a diagram's canvas. In this phase it shows the diagram,
 * to look at, pan and zoom: drawing on it, and the images it holds, come with editing.
 */

import "@excalidraw/excalidraw/index.css";
import "./canvas.css";
import { Excalidraw } from "@excalidraw/excalidraw";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import { type Data, WholeDialog } from "@portalr/ui";
import { type RefObject, useSyncExternalStore } from "react";

declare global {
  interface Window {
    EXCALIDRAW_ASSET_PATH: string;
  }
}

// The faces are the app's own copy (excalidraw.ts), never a CDN's.
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

/** A diagram's elements, as the canvas takes them; anything else in its data is passed over. */
function elementsOf(data: Data): ExcalidrawElement[] {
  const held = data.elements;
  if (typeof held !== "object" || held === null || Array.isArray(held)) return [];
  return Object.values(held).filter(
    (element): element is ExcalidrawElement =>
      typeof element === "object" && element !== null && !Array.isArray(element),
  );
}

function Canvas({ data, describedBy }: { data: Data; describedBy: string }) {
  const theme = useSyncExternalStore(watchScheme, scheme);
  return (
    <section className="absolute inset-0" aria-label="Canvas" aria-describedby={describedBy}>
      <Excalidraw
        initialData={{ elements: elementsOf(data), scrollToContent: true }}
        viewModeEnabled
        zenModeEnabled
        langCode="en"
        theme={theme}
        detectScroll={false}
        handleKeyboardGlobally={false}
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
      <Canvas data={data} describedBy={describedBy} />
    </WholeDialog>
  );
}
