import { keys, type Signed } from "@portalr/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Component, type ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { RunStreams, useAct, useRuns } from "./run-streams";
import { refusedAs } from "./runs";
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

/** The page's queries, which a live event makes stale. */
let queryClient: QueryClient;

function Queries({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  queryClient = new QueryClient();
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
    { wrapper: Queries },
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

test("a run's end, live, makes what the runs filed in a tracker stale", async () => {
  const filed = keys.relayr.filed("acme", "notes");
  queryClient.setQueryData(filed, { tracker: "plane", items: [] });
  const screen = await render(
    <RunStreams surfaces={SURFACES} signed={SIGNED} tenant="acme" workspace="notes">
      <Count />
    </RunStreams>,
    { wrapper: Queries },
  );
  await expect.element(screen.getByText("1 runs")).toBeVisible();
  expect(queryClient.getQueryState(filed)?.isInvalidated).toBe(false);
  FakeSocket.sockets[0]?.push(frame(2, { type: "reflexr:run_succeeded", run_id: "r1" }));
  await expect.poll(() => queryClient.getQueryState(filed)?.isInvalidated).toBe(true);
});

type Act = ReturnType<typeof useAct>;

function Harness({ into }: { into: { act?: Act } }) {
  into.act = useAct(refusedAs);
  return null;
}

test("a command's id is not let go while it is unanswered, and goes with its answer", async () => {
  const into: { act?: Act } = {};
  await render(
    <RunStreams surfaces={SURFACES} signed={SIGNED} tenant="acme" workspace="notes">
      <Harness into={into} />
    </RunStreams>,
    { wrapper: Queries },
  );
  await expect.poll(() => FakeSocket.sockets.length).toBe(1);
  const command = { type: "retry_run", run_id: "r1" } as const;
  const answered = into.act?.send(command);
  await expect.poll(() => FakeSocket.sent.length).toBe(1);
  const first = FakeSocket.sent[0]?.id ?? "";
  // A release while it is on its way, as a dismissed dialog would make, lets nothing go.
  into.act?.release(command);
  // The connection drops and comes back: what was unanswered is sent again, under its own id.
  FakeSocket.sockets[0]?.end(1006);
  await expect.poll(() => FakeSocket.sent.length, { timeout: 5000 }).toBe(2);
  expect(FakeSocket.sent[1]?.id).toBe(first);
  // Its answer ends that id, and only that one.
  FakeSocket.sockets.at(-1)?.raw({ type: "command_result", command_id: first, ok: true });
  await answered;
  const next = into.act?.send(command);
  await expect.poll(() => FakeSocket.sent.length).toBe(3);
  expect(FakeSocket.sent[2]?.id).not.toBe(first);
  FakeSocket.sockets.at(-1)?.raw({
    type: "command_result",
    command_id: FakeSocket.sent[2]?.id,
    ok: true,
  });
  await next;
});
