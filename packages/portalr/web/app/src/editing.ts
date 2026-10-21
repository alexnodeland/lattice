/**
 * The one native file being edited in place on the page (portalr ADR-0055): a page runs one
 * app's build at a time, whatever entries it shows. Another may open only once that one has no
 * unsaved changes; opening it closes the one before.
 */

import { useSyncExternalStore } from "react";

/** The file being edited, by its artifact's id, its name, and whether it has unsaved changes. */
export interface Editing {
  readonly artifact: string;
  readonly name: string;
  readonly dirty: boolean;
}

let current: Editing | null = null;
const listeners = new Set<() => void>();

function set(next: Editing | null) {
  current = next;
  for (const listener of listeners) {
    listener();
  }
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** The file being edited on the page, or null. */
export const useEditing = (): Editing | null => useSyncExternalStore(subscribe, () => current);

/**
 * Start editing a file: refused, with the file whose unsaved changes stand in the way, while
 * another has them; otherwise any other editor closes.
 */
export function startEditing(artifact: string, name: string): Editing | null {
  if (current !== null && current.artifact !== artifact && current.dirty) {
    return current;
  }
  set({ artifact, name, dirty: false });
  return null;
}

/** Say whether the file being edited has unsaved changes. */
export function editingDirty(artifact: string, dirty: boolean): void {
  if (current?.artifact === artifact && current.dirty !== dirty) {
    set({ ...current, dirty });
  }
}

/** Stop editing a file, if it is the one being edited. */
export function stopEditing(artifact: string): void {
  if (current?.artifact === artifact) {
    set(null);
  }
}
