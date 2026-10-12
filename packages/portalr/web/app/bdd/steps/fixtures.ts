/** What a scenario's steps share: the note the agent proposed an edit to, once it has. */

import { test as base, createBdd } from "playwright-bdd";

export const test = base.extend<{ scenario: { note: string | null } }>({
  scenario: async ({ page: _page }, use) => {
    await use({ note: null });
  },
});

export const { Given, When, Then } = createBdd(test);
