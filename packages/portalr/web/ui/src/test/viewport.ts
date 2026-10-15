import { onTestFinished } from "vitest";
import { page } from "vitest/browser";

/** The viewport a test starts at, which one that sets its own puts back. */
const DEFAULT_VIEWPORT = { width: 414, height: 896 } as const;

/** Sets the viewport for the rest of a test, and puts the default back when it finishes. */
export async function viewport(width: number, height = 800): Promise<void> {
  await page.viewport(width, height);
  onTestFinished(() => page.viewport(DEFAULT_VIEWPORT.width, DEFAULT_VIEWPORT.height));
}
