/** What a scenario's steps share: the note the agent proposed an edit to, once it has. */

import { test as base, createBdd } from "playwright-bdd";

export const test = base.extend<{ scenario: { note: string | null } }>({
  // Playwright reads a fixture's dependencies from its first parameter, and Biome refuses an
  // empty pattern there: `page`, which every scenario has, stands in.
  scenario: async ({ page: _page }, use) => {
    await use({ note: null });
  },
});

export const { Given, When, Then } = createBdd(test);
