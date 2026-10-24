/**
 * What the others are changing right now, drawn over the canvas (portalr ADR-0078): each peer's
 * `editing`, the arrow mid-drag or the text mid-typing, as a faint picture of its own, never in
 * the scene, so nothing of it is ever saved as this person's. A peer's elements are anyone's to
 * write, so they are taken as the canvas takes any diagram's first: no link, no embedded page,
 * no image, nothing out of reach. A peer's last picture stays until a revision newer than the
 * one it drew on arrives, so a stroke doesn't vanish between its pointer going up and its save.
 */

import { exportToSvg, getCommonBounds, sceneCoordsToViewportCoords } from "@excalidraw/excalidraw";
import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Ghost } from "../presence";

/** What a picture holds, as one text: each element by its id and version. */
const signature = (elements: readonly { id: string; version: number }[]) =>
  elements.map((element) => `${element.id}:${element.version}`).join(" ");

// Styles of their own, not the kit's classes, which would add to the stylesheet every page loads.
const OVER = {
  position: "absolute",
  inset: 0,
  zIndex: 5,
  overflow: "hidden",
  pointerEvents: "none",
} as const;

const LABEL = {
  position: "absolute",
  top: 0,
  left: 0,
  transform: "translateY(-100%)",
  padding: "0 4px",
  borderRadius: 2,
  background: "var(--surface)",
  color: "var(--muted)",
  fontSize: 12,
} as const;

/** One peer's picture, placed where its elements are in the scene, as the canvas is scrolled. */
function Picture({ api, ghost }: { api: ExcalidrawImperativeAPI; ghost: Ghost }) {
  const box = useRef<HTMLDivElement>(null);
  const drawn = useMemo(() => ghost.elements, [signature(ghost.elements)]);
  const [view, setView] = useState(() => api.getAppState());
  useEffect(() => api.onScrollChange(() => setView(api.getAppState())), [api]);
  useEffect(() => {
    let current = true;
    void exportToSvg({
      elements: drawn,
      appState: { exportBackground: false, exportWithDarkMode: false },
      files: null,
      exportPadding: 0,
      // The page's faces, not copies of them in a <style>, which its policy refuses.
      skipInliningFonts: true,
    })
      .then((svg: SVGSVGElement) => {
        if (!current || box.current === null) return;
        svg.setAttribute("aria-hidden", "true");
        // Its own <style>, which even with no faces inlined it writes, and which the page's
        // policy refuses (the CSP harness says so): the canvas has its faces already.
        for (const style of svg.querySelectorAll("style")) style.remove();
        box.current.replaceChildren(svg);
      })
      // One Excalidraw can't draw is simply not drawn: the canvas goes on.
      .catch(() => undefined);
    return () => {
      current = false;
    };
    // Drawn again as what it holds changes, not with every frame that says it again.
  }, [drawn]);
  const [minX, minY] = getCommonBounds(ghost.elements);
  const at = sceneCoordsToViewportCoords({ sceneX: minX, sceneY: minY }, view);
  return (
    <div
      data-peer={ghost.peer}
      style={{
        position: "absolute",
        opacity: 0.5,
        left: at.x - view.offsetLeft,
        top: at.y - view.offsetTop,
        transform: `scale(${view.zoom.value})`,
        transformOrigin: "0 0",
      }}
    >
      <div ref={box} />
      <span style={LABEL}>{ghost.name}</span>
    </div>
  );
}

/** Every peer's picture, over the canvas: a chunk of its own, fetched once someone draws. */
export default function Ghosts({
  api,
  ghosts,
}: {
  api: ExcalidrawImperativeAPI;
  ghosts: ReadonlyMap<string, Ghost>;
}) {
  return (
    <div style={OVER}>
      {[...ghosts.values()].map((ghost) => (
        <Picture key={ghost.peer} api={api} ghost={ghost} />
      ))}
    </div>
  );
}
