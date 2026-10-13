/**
 * How the people the scenarios' scripts sign up sign in: each by their name, at portalr.test,
 * on app's sign-in page or admin's, whichever the page's base is. admin's scenarios share it.
 */

import type { Page } from "@playwright/test";

export const email = (person: string) => `${person}@portalr.test`;

export const password = (person: string) => `${person}-password`;

/** Sign in on the page's own sign-in route, as `person`, with `secret`. */
export async function signIn(page: Page, person: string, secret = password(person)) {
  await page.goto("sign-in");
  await page.getByLabel("Email").fill(email(person));
  await page.getByLabel("Password").fill(secret);
  await page.getByRole("button", { name: "Sign in" }).click();
}
