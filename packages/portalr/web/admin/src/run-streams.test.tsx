import type { Signed } from "@portalr/client";
import { Component, type ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { RunStreams, useRuns } from "./run-streams";
import { FakeSocket, frame, stubSockets } from "./test/socket";

const SURFACES = { artifactr: "/artifactr/v1", reflexr: "/reflexr/v1", grantr: "", portalr: "" };

/** A session that is signed in and never changes. */
const SIGNED = {
  streamSession: (tenant: string) => ({ token: "t0k3n", tenant }),
  watch: () => () => undefined,
} as unknown as Signed;

function Count() {
  const { state } = useRuns();
  return <p>{Object.keys(state.runs).length} runs</p>;
}

class Catch extends Component<{ children: ReactNode }, { message: string | null }> {
  override state = { message: null };
  static getDerivedStateFromError(error: Error) {
    return { message: error.message };
  }
  override render() {
    return this.state.message === null ? this.props.children : <p>{this.state.message}</p>;
  }
}

beforeEach(() => {
  stubSockets({
    log: [frame(1, { type: "reflexr:run_started", run_id: "r1", rule: "x", attempt: 1 })],
    answer: () => null,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("another tenant's or workspace's stream is another stream, whatever key its caller gives", async () => {
  const props = { surfaces: SURFACES, signed: SIGNED };
  const screen = await render(
    <RunStreams {...props} tenant="acme" workspace="notes">
      <Count />
    </RunStreams>,
  );
  await expect.element(screen.getByText("1 runs")).toBeVisible();
  expect(FakeSocket.sockets.map((each) => new URL(each.url).pathname)).toEqual([
    "/reflexr/v1/workspaces/notes/stream",
  ]);
  await screen.rerender(
    <RunStreams {...props} tenant="acme" workspace="plans">
      <Count />
    </RunStreams>,
  );
  await expect.poll(() => FakeSocket.sockets.length).toBe(2);
  expect(FakeSocket.sockets[0]?.open).toBe(false);
  expect(FakeSocket.sockets[1]?.url).toContain("/workspaces/plans/stream");
  await screen.rerender(
    <RunStreams {...props} tenant="globex" workspace="plans">
      <Count />
    </RunStreams>,
  );
  await expect.poll(() => FakeSocket.sockets.length).toBe(3);
  expect(FakeSocket.sockets[2]?.url).toContain("tenant=globex");
  expect(FakeSocket.sockets.filter((each) => each.open)).toHaveLength(1);
});

test("runs are read inside a stream, and nowhere else", async () => {
  const screen = await render(
    <Catch>
      <Count />
    </Catch>,
  );
  await expect
    .element(screen.getByText("rule runs are read inside a workspace's stream"))
    .toBeVisible();
});
