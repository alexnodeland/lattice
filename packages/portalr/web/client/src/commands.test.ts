import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import { createCommands } from "./commands";
import { createApi } from "./rest";

/** What the server answers, by the command's id. */
const ANSWERS: Record<string, () => Response> = {
  done: () => Response.json({ type: "command_result", command_id: "done", ok: true }),
  problems: () =>
    Response.json(
      {
        type: "command_result",
        command_id: "problems",
        ok: false,
        rejection: {
          type: "validation_failed",
          message: "rule tickets:echo cannot be stored",
          errors: ["timeout is required", "when.throttle is required"],
        },
      },
      { status: 422 },
    ),
  conflict: () =>
    Response.json(
      {
        type: "command_result",
        command_id: "conflict",
        ok: false,
        rejection: { type: "invalid_state", message: "rule tickets:echo is at version 3" },
      },
      { status: 409 },
    ),
  unread: () =>
    Response.json(
      {
        detail: [
          {
            loc: ["body", "command", "install_rule", "rule", "when", "throttle"],
            msg: "Field required",
          },
          { loc: ["body", "command"], msg: "Unable to extract tag" },
        ],
      },
      { status: 422 },
    ),
  forbidden: () =>
    Response.json(
      {
        type: "command_result",
        command_id: "forbidden",
        ok: false,
        rejection: { type: "forbidden", message: "bob may not reflexr:archive_rule" },
      },
      { status: 403 },
    ),
  unsigned: () => Response.json({ detail: "no one is signed in" }, { status: 401 }),
  missing: () =>
    Response.json({ detail: { message: "workspace gone does not exist" } }, { status: 404 }),
  broken: () => new Response("upstream gone", { status: 502 }),
  odd: () => Response.json({ something: "else" }, { status: 400 }),
};

const sent: { url: URL; tenant: string | null; body: { command_id: string } }[] = [];
let server: Server<unknown>;
let commands: ReturnType<typeof createCommands>;
let unsigned = 0;

beforeAll(() => {
  server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const body = (await request.json()) as { command_id: string };
      sent.push({ url: new URL(request.url), tenant: request.headers.get("x-tenant"), body });
      return ANSWERS[body.command_id]?.() ?? new Response(null, { status: 500 });
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  commands = createCommands(
    createApi(
      { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
      () => ({ token: "t0k3n" }),
    ),
    () => {
      unsigned += 1;
    },
  );
});

afterAll(() => server.stop());

const archive = { type: "archive_rule", rule: "tickets:echo" } as const;

test("a command goes to its workspace in its tenant, and is done when carried out", async () => {
  const answer = await commands.reflexr.send("acme", "notes", archive, "done");
  expect(answer.outcome).toBe("done");
  expect(sent.at(-1)?.url.pathname).toBe("/reflexr/v1/workspaces/notes/commands");
  expect(sent.at(-1)?.tenant).toBe("acme");
  expect(sent.at(-1)?.body).toEqual({ type: "command", command_id: "done", command: archive });
});

test("a command's id is its own unless one is given", async () => {
  await commands.reflexr.send("acme", "notes", archive);
  expect(sent.at(-1)?.body.command_id).toMatch(/^[0-9a-f-]{36}$/);
});

test("a refusal gives each reason: a rejection's problems, or its message", async () => {
  expect(await commands.reflexr.send("acme", "notes", archive, "problems")).toEqual({
    outcome: "refused",
    status: 422,
    reasons: ["timeout is required", "when.throttle is required"],
  });
  expect(await commands.reflexr.send("acme", "notes", archive, "conflict")).toEqual({
    outcome: "refused",
    status: 409,
    reasons: ["rule tickets:echo is at version 3"],
  });
});

test("an archive refused as forbidden, or over another version, says so", async () => {
  expect(await commands.reflexr.send("acme", "notes", archive, "forbidden")).toEqual({
    outcome: "refused",
    status: 403,
    reasons: ["bob may not reflexr:archive_rule"],
  });
  expect(await commands.reflexr.send("acme", "notes", archive, "conflict")).toMatchObject({
    status: 409,
  });
});

test("a refusal's detail is its reason, and one for no one signed in ends the session", async () => {
  expect(await commands.reflexr.send("acme", "gone", archive, "missing")).toEqual({
    outcome: "refused",
    status: 404,
    reasons: ["workspace gone does not exist"],
  });
  expect(unsigned).toBe(0);
  expect(await commands.reflexr.send("acme", "notes", archive, "unsigned")).toEqual({
    outcome: "refused",
    status: 401,
    reasons: ["no one is signed in"],
  });
  expect(unsigned).toBe(1);
});

test("a server that can't be reached refuses, rather than throwing", async () => {
  const closed = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response() });
  const origin = `http://127.0.0.1:${closed.port}`;
  closed.stop(true);
  const away = createCommands(
    createApi({ artifactr: origin, reflexr: origin, grantr: origin }, () => ({ token: "t" })),
  );
  expect(await away.reflexr.send("acme", "notes", archive)).toEqual({
    outcome: "refused",
    status: 0,
    reasons: ["The server couldn't be reached."],
  });
});

test("a body that isn't a command is refused with where in it each error is", async () => {
  expect(await commands.reflexr.send("acme", "notes", archive, "unread")).toEqual({
    outcome: "refused",
    status: 422,
    reasons: ["rule.when.throttle: Field required", "Unable to extract tag"],
  });
});

test("an answer that isn't the library's says its status", async () => {
  for (const [id, status] of [
    ["broken", 502],
    ["odd", 400],
  ] as const) {
    expect(await commands.reflexr.send("acme", "notes", archive, id)).toEqual({
      outcome: "refused",
      status,
      reasons: [`The server answered ${status}.`],
    });
  }
});
