/**
 * What a scenario's steps share: the note the agent proposed an edit to, the document it drafted
 * and the name a download of it was saved under, the thread it started, the rule run it set off,
 * once it has, the stored rule it installed, and the tracker item a run filed.
 */

import { test as base, createBdd } from "playwright-bdd";

export const test = base.extend<{
  scenario: {
    note: string | null;
    document: string | null;
    /** The name the browser was told to save a download under. */
    downloaded: string | null;
    thread: string | null;
    run: string | null;
    rule: string | null;
    /** Where the thread a scenario started is, to open it by its address. */
    threadUrl: string | null;
    /** What people call the tracker item a run filed, such as `OPS-3`. */
    item: string | null;
  };
}>({
  // Playwright reads a fixture's dependencies from its first parameter, and Biome refuses an
  // empty pattern there: `page`, which every scenario has, stands in.
  scenario: async ({ page: _page }, use) => {
    await use({
      note: null,
      document: null,
      downloaded: null,
      thread: null,
      run: null,
      rule: null,
      threadUrl: null,
      item: null,
    });
  },
});

export const { Given, When, Then } = createBdd(test);

/** What a scenario started, or why a step that needs it can't run. */
export function started<T>(what: T | null, step = "start a thread of their own"): T {
  if (what === null) {
    throw new Error(`nothing was started: ${step} first`);
  }
  return what;
}
