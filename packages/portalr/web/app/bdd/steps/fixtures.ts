/**
 * What a scenario's steps share: the note the agent proposed an edit to, the thread it started,
 * the rule run it set off, once it has, and the stored rule it installed.
 */

import { test as base, createBdd } from "playwright-bdd";

export const test = base.extend<{
  scenario: {
    note: string | null;
    thread: string | null;
    run: string | null;
    rule: string | null;
  };
}>({
  // Playwright reads a fixture's dependencies from its first parameter, and Biome refuses an
  // empty pattern there: `page`, which every scenario has, stands in.
  scenario: async ({ page: _page }, use) => {
    await use({ note: null, thread: null, run: null, rule: null });
  },
});

export const { Given, When, Then } = createBdd(test);
