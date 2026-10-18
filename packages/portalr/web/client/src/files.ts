/**
 * Native files' bytes, as the UIs move them (lattice RFC-0003). Every route asks for the session
 * and the tenant, so nothing is linked to directly: a page is read and shown as a `data:` URL,
 * which the UIs' policy allows where it allows no `blob:`, and a version is read as a `Blob`, for
 * the app to save.
 */

/** A PNG's bytes as a `data:` URL, typed as a PNG whatever the response said. */
export function pngDataUrl(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  // In chunks, so a large page never passes more arguments than a call takes.
  for (let at = 0; at < view.length; at += 0x8000) {
    binary += String.fromCharCode(...view.subarray(at, at + 0x8000));
  }
  return `data:image/png;base64,${btoa(binary)}`;
}
