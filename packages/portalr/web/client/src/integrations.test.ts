import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, beforeAll, beforeEach, expect, test } from "vitest";
import { createCommands } from "./commands";
import { INTEGRATIONS } from "./generated/integrations";
import { changedIntegrations, enabledFrom } from "./integrations";
import { createQueries, keys, stale } from "./queries";
import { createApi } from "./rest";

const STATE = {
  key: "markdown:mermaid",
  description: "Mermaid: diagrams written as text in messages, drawn.",
  default: false,
  installed: true,
  tenant: null,
  workspace: { on: true, by: { kind: "user", id: "alice" }, at: "2026-10-17T12:00:00Z" },
  enabled: true,
};

const asked: { method: string; path: string; tenant: string | null; body: string }[] = [];
let server: Server<unknown>;
let queries: ReturnType<typeof createQueries>;
let commands: ReturnType<typeof createCommands>;

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    async fetch(request) {
      const path = decodeURIComponent(new URL(request.url).pathname);
      const tenant = request.headers.get("x-tenant");
      asked.push({ method: request.method, path, tenant, body: await request.text() });
      if (tenant === "down") {
        return new Response("upstream gone", { status: 503 });
      }
      if (path.endsWith("/enabled-integrations")) {
        return Response.json({ "markdown:mermaid": true, "ui:forms": false });
      }
      if (request.method === "PUT" && path.endsWith("/integrations/nope")) {
        return Response.json({ detail: "nope is not an integration" }, { status: 422 });
      }
      return request.method === "PUT" ? Response.json(STATE) : Response.json([STATE]);
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  const api = createApi(
    { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
    () => ({ token: "t0k3n" }),
  );
  queries = createQueries(api);
  commands = createCommands(api);
});

afterAll(() => {
  server.stop(true);
});

beforeEach(() => {
  asked.length = 0;
});

test("each integration is what grantr answered, and where it didn't answer, its default", () => {
  const enabled = enabledFrom({ "markdown:mermaid": true, "ui:forms": false });
  expect(enabled("markdown:mermaid")).toBe(true);
  expect(enabled("ui:forms")).toBe(false);
  expect(enabled("markdown:math")).toBe(true);
  expect(enabled("ui:mini-apps")).toBe(false);
});

test("unread, every integration is its registry default: mini apps and Mermaid off", () => {
  const enabled = enabledFrom(undefined);
  expect(INTEGRATIONS.map(({ key }) => [key, enabled(key)])).toEqual(
    INTEGRATIONS.map((known) => [known.key, known.default]),
  );
  expect(enabled("ui:mini-apps")).toBe(false);
  expect(enabled("markdown:mermaid")).toBe(false);
});

test("a workspace's integrations are read once, in its tenant, and kept", async () => {
  const queryClient = new QueryClient();
  const read = queries.grantr.enabledIntegrations("acme", "team/notes");
  expect(await queryClient.fetchQuery(read)).toEqual({
    "markdown:mermaid": true,
    "ui:forms": false,
  });
  await queryClient.fetchQuery(read);
  await queryClient.ensureQueryData(read);
  expect(asked).toEqual([
    {
      method: "GET",
      path: "/grantr/v1/tenants/acme/workspaces/team/notes/enabled-integrations",
      tenant: "acme",
      body: "",
    },
  ]);
});

test("a read that fails leaves each integration its default", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const read = queries.grantr.enabledIntegrations("down", "notes");
  await expect(queryClient.fetchQuery(read)).rejects.toThrow("503");
  const enabled = enabledFrom(queryClient.getQueryData(read.queryKey));
  expect(enabled("markdown:mermaid")).toBe(false);
  expect(enabled("excalidraw")).toBe(false);
  expect(enabled("markdown:math")).toBe(true);
});

test("a command refused as not_enabled makes the workspace's integrations stale, and no other", () => {
  const refused = (type: string) => ({
    type: "command_result" as const,
    command_id: "c_1",
    ok: false,
    rejection: { type, message: "excalidraw is not available in this workspace" },
  });
  expect(stale.refusal("acme", "notes", refused("not_enabled"))).toEqual([
    keys.grantr.enabledIntegrations("acme", "notes"),
  ]);
  expect(stale.refusal("acme", "notes", refused("forbidden"))).toEqual([]);
  expect(
    stale.refusal("acme", "notes", { type: "command_result", command_id: "c", ok: false }),
  ).toEqual([]);
});

test("the tenant's and a workspace's integrations are read at their own paths, in the tenant", async () => {
  const queryClient = new QueryClient();
  expect(await queryClient.fetchQuery(queries.grantr.integrations("acme"))).toEqual([STATE]);
  await queryClient.fetchQuery(queries.grantr.integrations("acme", "notes"));
  expect(asked.map(({ path, tenant }) => [path, tenant])).toEqual([
    ["/grantr/v1/tenants/acme/integrations", "acme"],
    ["/grantr/v1/tenants/acme/workspaces/notes/integrations", "acme"],
  ]);
});

test("an integration is set on the tenant, in a workspace, or back to inherited", async () => {
  expect(await commands.grantr.setIntegration("acme", "markdown:mermaid", true)).toEqual({
    outcome: "done",
    result: STATE,
  });
  await commands.grantr.setIntegration("acme", "markdown:mermaid", false, "notes");
  await commands.grantr.setIntegration("acme", "markdown:mermaid", null, "notes");
  expect(asked.map(({ method, path, tenant, body }) => [method, path, tenant, body])).toEqual([
    ["PUT", "/grantr/v1/tenants/acme/integrations/markdown:mermaid", "acme", '{"on":true}'],
    [
      "PUT",
      "/grantr/v1/tenants/acme/workspaces/notes/integrations/markdown:mermaid",
      "acme",
      '{"on":false}',
    ],
    [
      "PUT",
      "/grantr/v1/tenants/acme/workspaces/notes/integrations/markdown:mermaid",
      "acme",
      '{"on":null}',
    ],
  ]);
});

test("a setting grantr refuses says why", async () => {
  expect(await commands.grantr.setIntegration("acme", "nope", true)).toEqual({
    outcome: "refused",
    status: 422,
    reasons: ["nope is not an integration"],
  });
});

test("a setting makes every read of the tenant's integrations stale, and nothing else", async () => {
  const queryClient = new QueryClient();
  const read = [
    keys.grantr.integrationStates("acme"),
    keys.grantr.integrationStates("acme", "notes"),
    keys.grantr.enabledIntegrations("acme", "plans"),
    keys.grantr.members("acme"),
    keys.grantr.enabledIntegrations("globex", "notes"),
  ];
  for (const queryKey of read) {
    queryClient.setQueryData(queryKey, {});
  }
  const answer = await changedIntegrations(queryClient, "acme", Promise.resolve("done"));
  expect(answer).toBe("done");
  expect(read.map((queryKey) => queryClient.getQueryState(queryKey)?.isInvalidated)).toEqual([
    true,
    true,
    true,
    false,
    false,
  ]);
});
