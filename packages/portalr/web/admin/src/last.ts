/**
 * admin's last choice in this browser: a tenant's id, or `deployment` for every tenant. It is
 * admin's own, apart from the app's, and opens admin there next time if it is still theirs.
 */

const KEY = "portalr-admin-tenant";

/** The last choice, or null when there is none or storage can't be read. */
export function lastChoice(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Keep a choice where storage allows; without storage it lasts as long as the page. */
export function remember(choice: string): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    // Nothing kept: admin opens on its own choice next time.
  }
}
