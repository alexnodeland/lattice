// The Excalidraw this worker draws with: its package.json's pin, which scripts/check-template
// holds to versions.env's EXCALIDRAW_VERSION, and so to portalr's canvas.

import manifest from "../package.json" with { type: "json" };

export const EXCALIDRAW: string = manifest.dependencies["@excalidraw/excalidraw"];
