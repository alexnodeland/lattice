/** Items in a tracker in each state the links show, for their tests and their screenshots. */

import type { TrackerItem } from "../tracker-items";

export const FILED: readonly TrackerItem[] = [
  { tracker: "plane", name: "OPS-12", link: "https://plane.example/acme/browse/OPS-12/" },
  { tracker: "vikunja", name: "#41", link: "https://vikunja.example/tasks/41" },
  {
    tracker: "plane",
    name: "OPS-9",
    link: "https://plane.example/acme/browse/OPS-9/",
    deleted: true,
  },
];

/** An item whose address no browser opens as a page, and one with none: names alone. */
export const UNLINKED: readonly TrackerItem[] = [
  { tracker: "plane", name: "OPS-3", link: "javascript:alert(1)" },
  { tracker: "linear", name: "ENG-7", link: null },
];
