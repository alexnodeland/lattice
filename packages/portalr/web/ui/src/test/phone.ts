// Each phone file starts at the window's own scale. Chromium, emulating a phone, keeps the page's
// zoom when a file's `page.viewport` narrows and widens the window, and the next file a worker runs
// shares that page (since Vitest 5.0.4, each browser a worker, CI's few run many files each):
// zoomed in, a sheet's foot is out of the window, and out of Playwright's reach. A setup file of
// every phone project, ui's, app's and admin's, which each name by its path.
import { beforeAll } from "vitest";
import { cdp } from "vitest/browser";

beforeAll(async () => {
  await cdp().send("Emulation.setPageScaleFactor", { pageScaleFactor: 1 });
});
