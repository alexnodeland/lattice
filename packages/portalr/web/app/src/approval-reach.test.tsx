/**
 * An approval waiting as its thread opens is in the window, its Deny and Approve neither covered
 * by the composer's dock nor missing beside it, at every width (portalr ADR-0087): in one column
 * the dock stays in the flow under the card; from 1100 pixels the card floats in the pane's corner.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open } from "./test/app";
import { AT } from "./test/files";

afterEach(() => {
  vi.unstubAllGlobals();
});

const at = (seq: number, actor: unknown, event: unknown) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-27T09:00:00Z",
  workspace_id: "notes",
  actor,
  event,
});
const alice = { kind: "user", id: "alice" };
const agent = { kind: "agent", id: "agent", run_id: "run_a" };
const LOG = [
  at(1, alice, { type: "thread_created", thread_id: "thr_a", title: "Pricing page copy" }),
  at(2, alice, {
    type: "message_posted",
    thread_id: "thr_a",
    message_id: "m1",
    content: "Publish the pricing page copy v3.",
  }),
  at(3, agent, { type: "run_started", run_id: "run_a", thread_id: "thr_a" }),
  at(4, agent, {
    type: "artifact_created",
    artifact_id: "note_2",
    kind: "note",
    version: 1,
    thread_id: "thr_a",
    run_id: "run_a",
  }),
  at(5, agent, {
    type: "run_paused",
    run_id: "run_a",
    thread_id: "thr_a",
    requests: [
      {
        kind: "approval",
        tool_call_id: "a1",
        tool_name: "publish",
        args: { channel: "customers" },
        review: { app: "the site", runs: "It publishes.", risk: "network" },
      },
    ],
  }),
];
const NOTE =
  "# Pricing\n\nSimple plans.\n\n## Annual\n\nTwo months free.\n\n## Monthly\n\nCancel any time.";
const serve = async (request: Request, path: string) => {
  if (path === "/grantr/v1/checks") {
    return Response.json(((await request.json()) as unknown[]).map(() => true));
  }
  if (path === `${AT}/artifacts/note_2/revisions`) {
    return Response.json([
      {
        artifact_id: "note_2",
        version: 1,
        kind: "note",
        data: { text: NOTE },
        archived: false,
        actor: { kind: "agent", thread_id: "thr_a", run_id: "run_a" },
      },
    ]);
  }
  return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : undefined;
};

/** Whether the button is in the window and is what a press at its centre lands on. */
function reachable(button: HTMLElement) {
  const box = button.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;
  const inWindow = box.top >= 0 && box.bottom <= window.innerHeight && box.width > 0;
  return inWindow && button.contains(document.elementFromPoint(x, y));
}

for (const width of [320, 393, 430, 768, 1024, 1100, 1440]) {
  test(`at ${width}px an approval's Deny and Approve are in the window, uncovered`, async () => {
    await page.viewport(width, width < 1024 ? 740 : 800);
    const { screen } = await open("/t/acme/w/notes/threads/thr_a", serve, () => null, {
      artifactrLog: LOG,
    });
    const card = screen.getByRole("region", { name: "Approve publish?" });
    await expect.element(card).toBeInTheDocument();
    await expect.element(screen.getByText("Two months free.").first()).toBeInTheDocument();
    for (const name of ["Approve", "Deny"]) {
      const button = card.getByRole("button", { name }).element() as HTMLElement;
      await expect.poll(() => reachable(button), { timeout: 5_000 }).toBe(true);
    }
  });
}
