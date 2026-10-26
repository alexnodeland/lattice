/**
 * How far into each thread this browser has read (portalr ADR-0080): the `seq` the thread was
 * active at when its page was last shown live, kept in localStorage per workspace, so the list
 * can mark what has moved since. The browser's alone: nothing is sent, and storage that can't be
 * read or written marks nothing.
 */

const key = (tenant: string, workspace: string) => `portalr:seen:${tenant}/${workspace}`;

export function readSeen(tenant: string, workspace: string): Readonly<Record<string, number>> {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(key(tenant, workspace)) ?? "{}");
    return typeof stored === "object" && stored !== null ? (stored as Record<string, number>) : {};
  } catch {
    return {};
  }
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
