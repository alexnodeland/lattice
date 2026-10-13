/** admin's scenarios' steps, and what a scenario's steps share: the names it made afresh. */

import { test as base, createBdd } from "playwright-bdd";

export const test = base.extend<{ made: Map<string, string> }>({
  // Playwright reads a fixture's dependencies from its first parameter, and Biome refuses an
  // empty pattern there: `page`, which every scenario has, stands in.
  made: async ({ page: _page }, use) => {
    await use(new Map());
  },
});

export const { Given, When, Then } = createBdd(test);

/** The name a scenario made afresh for `what`, such as a principal; it must have made one. */
export const madeAs = (made: Map<string, string>, what: string) => {
  const name = made.get(what);
  if (name === undefined) {
    throw new Error(`no ${what} was made: make one first`);
  }
  return name;
};
