/**
 * A thread's model as this browser remembers it (portalr ADR-0086): what the composer's picker, a
 * select on a desktop, and its pill and sheet on a phone, both read and write.
 */

/** The model a message that names none answers with. */
export const DEFAULT = "default";

/** Where this browser remembers a thread's model. */
const key = (thread: string) => `portalr:model:${thread}`;

/** The model last chosen in a thread here, or null; storage that can't be read has none. */
export function remembered(thread: string): string | null {
  try {
    return localStorage.getItem(key(thread));
  } catch {
    return null;
  }
}

/** Remember a thread's model here; the default is remembered as nothing. */
export function remember(thread: string, model: string): void {
  try {
    if (model === DEFAULT) {
      localStorage.removeItem(key(thread));
    } else {
      localStorage.setItem(key(thread), model);
    }
  } catch {
    // Without storage the choice lasts as long as the page.
  }
}
