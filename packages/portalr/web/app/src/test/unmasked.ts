/**
 * A coarse check of a batch, apart from the recorder's masking: the first key in the events that
 * carries a word, an address or a `data-*` value unmasked, or null. It is not the relay's rule,
 * which is an allow-list (portalr's `analytics/replay.py`, held by its own tests); it says that
 * what a real page's recording sent has none of the plain mistakes in it.
 */

const WORDED = new Set([
  ...["textContent", "value", "text", "placeholder", "title", "alt", "aria-label"],
  ...["aria-description", "aria-valuetext", "href", "src", "srcset", "content", "label", "name"],
]);

export function unmasked(events: unknown[]): string | null {
  const stack: unknown[] = [...events];
  while (stack.length > 0) {
    const item = stack.pop();
    if (Array.isArray(item)) {
      stack.push(...item);
      continue;
    }
    if (item === null || typeof item !== "object") {
      continue;
    }
    const node = item as Record<string, unknown>;
    for (const [key, value] of Object.entries(node)) {
      if (typeof value === "object" && value !== null) {
        stack.push(value);
      } else if (typeof value === "string" && !/^[\s*]*$/.test(value)) {
        const doctype =
          key === "name" &&
          node.type === 1 &&
          "publicId" in node &&
          "systemId" in node &&
          /^[A-Za-z][A-Za-z0-9]{0,31}$/.test(value);
        const page =
          doctype ||
          (key === "textContent" && (node.isStyle === true || value === "SCRIPT_PLACEHOLDER"));
        if (
          !page &&
          (WORDED.has(key) || (key.startsWith("data-") && key !== "data-portalr-replay"))
        ) {
          return key;
        }
      }
    }
  }
  return null;
}
