/**
 * How far into each thread this browser has read (portalr ADR-0080): the `seq` the thread was
 * active at when its page was last shown live, kept in localStorage per workspace, so the list
 * can mark what has moved since. The browser's alone: nothing is sent, and storage that can't be
 * read or written marks nothing.
 */

const key = (tenant: string, workspace: string) => `portalr:seen:${tenant}/${workspace}`;

// What was read last, kept by its text, so a read that finds storage unchanged is the same object.
let last: { readonly raw: string; readonly seen: Readonly<Record<string, number>> } | null = null;

export function readSeen(tenant: string, workspace: string): Readonly<Record<string, number>> {
  try {
    const raw = localStorage.getItem(key(tenant, workspace)) ?? "{}";
    if (last?.raw !== raw) {
      const stored: unknown = JSON.parse(raw);
      last = {
        raw,
        seen:
          typeof stored === "object" && stored !== null ? (stored as Record<string, number>) : {},
      };
    }
    return last.seen;
  } catch {
    return {};
  }
}

/** Hears another tab's marks, through the browser's storage event. */
export function subscribeToSeen(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

export function markSeen(tenant: string, workspace: string, thread: string, seq: number): void {
  try {
    const seen = readSeen(tenant, workspace);
    if (seen[thread] !== seq) {
      localStorage.setItem(key(tenant, workspace), JSON.stringify({ ...seen, [thread]: seq }));
    }
  } catch {
    // Without storage, nothing is marked.
  }
}
