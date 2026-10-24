import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import { createCommands, orThrow, refusal } from "./commands";
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
          errors: [
            { loc: ["rule", "timeout"], msg: "timeout is required", type: "missing" },
            {
              loc: ["rule", "when", "throttle"],
              msg: "when.throttle is required",
              type: "missing",
            },
          ],
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

/** What grantr answers, by the last part of the path. */
const GRANTR: Record<string, () => Response> = {
  grants: () => Response.json({ seq: 1 }, { status: 201 }),
  revocations: () => Response.json({ seq: 2 }),
  restrictions: () =>
    Response.json(
      { detail: { type: "forbidden", message: "bob may not grantr:restrict" } },
      { status: 403 },
    ),
};

const sent: {
  method: string;
  url: URL;
  tenant: string | null;
  body: { command_id: string };
}[] = [];
let server: Server<unknown>;
let commands: ReturnType<typeof createCommands>;
let unsigned = 0;

beforeAll(() => {
  server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const text = await request.text();
      const body = (text ? JSON.parse(text) : null) as { command_id: string };
      const url = new URL(request.url);
      sent.push({ method: request.method, url, tenant: request.headers.get("x-tenant"), body });
      if (url.pathname === "/portalr/v1/deployment/tenants") {
        return body && (body as unknown as { tenant: string }).tenant === "acme"
          ? Response.json({ detail: { type: "invalid", message: "acme exists" } }, { status: 422 })
          : Response.json({ tenant: "initech", owner: "dan" }, { status: 201 });
      }
      if (url.pathname === "/portalr/v1/invites") {
        return Response.json({ tenant: "acme", user: "newcomer" }, { status: 201 });
      }
      if (url.pathname.startsWith("/grantr/v1/tenants/unsigned/")) {
        return Response.json({ detail: "no one is signed in" }, { status: 401 });
      }
      if (url.pathname.startsWith("/grantr/")) {
        const last = url.pathname.split("/").at(-1) ?? "";
        const answered = GRANTR[last]?.();
        if (answered) {
          return answered;
        }
        return request.method === "POST" && last === "keys"
          ? Response.json({ key: "sk_secret", entry: { seq: 4 } }, { status: 201 })
          : Response.json({ seq: 3 });
      }
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

test("a refusal says the kit's sentence for its reason code, never the server's words", async () => {
  expect(await commands.reflexr.send("acme", "notes", archive, "problems")).toEqual({
    outcome: "refused",
    status: 422,
    reasons: ["What was asked for isn't valid: rule.timeout, rule.when.throttle."],
  });
  expect(await commands.reflexr.send("acme", "notes", archive, "conflict")).toEqual({
    outcome: "refused",
    status: 409,
    reasons: ["That can't be done as things stand."],
  });
});

test("an archive refused as forbidden, or over another version, says so", async () => {
  expect(await commands.reflexr.send("acme", "notes", archive, "forbidden")).toEqual({
    outcome: "refused",
    status: 403,
    reasons: ["You may not do this here."],
  });
  expect(await commands.reflexr.send("acme", "notes", archive, "conflict")).toMatchObject({
    status: 409,
  });
});

test("a refusal without a known code says what its status does, and one for no one signed in ends the session", async () => {
  expect(await commands.reflexr.send("acme", "gone", archive, "missing")).toEqual({
    outcome: "refused",
    status: 404,
    reasons: ["It isn't there: it may have been moved or archived."],
  });
  expect(unsigned).toBe(0);
  expect(await commands.reflexr.send("acme", "notes", archive, "unsigned")).toEqual({
    outcome: "refused",
    status: 401,
    reasons: ["You're not signed in. Sign in, then try again."],
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
    reasons: ["What was asked for isn't valid: rule.when.throttle."],
  });
});

test("an answer that isn't the library's says what its status does", async () => {
  for (const [id, status, said] of [
    ["broken", 502, "The server had a problem. Try again in a moment."],
    ["odd", 400, "Something went wrong. Try again in a moment."],
  ] as const) {
    expect(await commands.reflexr.send("acme", "notes", archive, id)).toEqual({
      outcome: "refused",
      status,
      reasons: [said],
    });
  }
});

test("grantr's grants, revocations and restrictions go to the tenant's own paths", async () => {
  const on = { kind: "thread", workspace: "notes", id: "thr_1" } as const;
  const grant = { role: "viewer", on, to: { kind: "user", id: "bob" } } as const;
  expect(await commands.grantr.grant("acme", grant)).toEqual({
    outcome: "done",
    result: { seq: 1 },
  });
  expect(sent.at(-1)).toMatchObject({ tenant: "acme", body: grant });
  expect(sent.at(-1)?.url.pathname).toBe("/grantr/v1/tenants/acme/grants");
  expect(await commands.grantr.revoke("acme", grant)).toEqual({
    outcome: "done",
    result: { seq: 2 },
  });
  expect(sent.at(-1)?.url.pathname).toBe("/grantr/v1/tenants/acme/revocations");
  expect(sent.at(-1)?.tenant).toBe("acme");
  expect(await commands.grantr.restrict("acme", { on, restricted: true })).toEqual({
    outcome: "refused",
    status: 403,
    reasons: ["You may not do this here."],
  });
  expect(sent.at(-1)?.url.pathname).toBe("/grantr/v1/tenants/acme/restrictions");
  expect(sent.at(-1)?.tenant).toBe("acme");
});

test("a grantr change refused for no one signed in ends the session", async () => {
  const before = unsigned;
  const on = { kind: "thread", workspace: "notes", id: "thr_1" } as const;
  expect(
    await commands.grantr.grant("unsigned", {
      role: "viewer",
      on,
      to: { kind: "user", id: "bob" },
    }),
  ).toMatchObject({ outcome: "refused", status: 401 });
  expect(unsigned).toBe(before + 1);
});

test("a refusal says what wasn't done, and each reason", () => {
  expect(
    refusal("The rule wasn't saved", {
      outcome: "refused",
      status: 422,
      reasons: ["timeout is required", "when.throttle is required"],
    }),
  ).toBe("The rule wasn't saved: timeout is required; when.throttle is required");
});

test("grantr's access commands go to the tenant's own paths, with its header", async () => {
  const bob = { kind: "user", id: "bob" } as const;
  const ci = { kind: "service_principal", id: "ci" } as const;
  const calls: [() => Promise<unknown>, string, string, unknown][] = [
    [() => commands.grantr.addMember("acme", ci), "POST", "/members", { member: ci }],
    [() => commands.grantr.removeMember("acme", bob), "DELETE", "/members/user/bob", null],
    [
      () => commands.grantr.removeMember("acme", ci),
      "DELETE",
      "/members/service_principal/ci",
      null,
    ],
    [
      () => commands.grantr.defineGroup("acme", "team", [bob]),
      "PUT",
      "/groups/team",
      { members: [bob] },
    ],
    [() => commands.grantr.deleteGroup("acme", "team"), "DELETE", "/groups/team", null],
    [() => commands.grantr.revokeKey("acme", "key_1"), "DELETE", "/keys/key_1", null],
    [
      () => commands.grantr.defineRole("acme", "triager", ["reflexr:retry_run"]),
      "PUT",
      "/roles/triager",
      { actions: ["reflexr:retry_run"] },
    ],
    [() => commands.grantr.deleteRole("acme", "triager"), "DELETE", "/roles/triager", null],
  ];
  for (const [call, method, path, body] of calls) {
    expect(await call()).toMatchObject({ outcome: "done" });
    expect(sent.at(-1)).toMatchObject({ method, tenant: "acme", body });
    expect(sent.at(-1)?.url.pathname).toBe(`/grantr/v1/tenants/acme${path}`);
  }
});

test("a key's secret is in the answer to issuing it", async () => {
  expect(await commands.grantr.issueKey("acme", "ci")).toEqual({
    outcome: "done",
    result: { key: "sk_secret", entry: { seq: 4 } },
  });
  expect(sent.at(-1)).toMatchObject({ method: "POST", body: { principal: "ci" } });
});

test("an invitation names its tenant, and answers whom it added", async () => {
  expect(await commands.portalr.invite("acme", "new@acme.test")).toEqual({
    outcome: "done",
    result: { tenant: "acme", user: "newcomer" },
  });
  expect(sent.at(-1)).toMatchObject({ tenant: "acme", body: { email: "new@acme.test" } });
  expect(sent.at(-1)?.url.pathname).toBe("/portalr/v1/invites");
});

test("creating a tenant names no tenant to act in, sends the email once, and answers the owner's id", async () => {
  expect(await commands.portalr.createTenant("initech", "dan@initech.com")).toEqual({
    outcome: "done",
    result: { tenant: "initech", owner: "dan" },
  });
  expect(sent.at(-1)).toMatchObject({
    tenant: null,
    body: { tenant: "initech", owner_email: "dan@initech.com" },
  });
  expect(sent.at(-1)?.url.pathname).toBe("/portalr/v1/deployment/tenants");
  expect(await commands.portalr.createTenant("acme", "dan@initech.com")).toMatchObject({
    outcome: "refused",
    status: 422,
    reasons: ["What was asked for isn't valid."],
  });
});

test("orThrow gives a done command's answer, and throws a refusal's words", () => {
  expect(orThrow("Not removed", { outcome: "done", result: 7 })).toBe(7);
  expect(() =>
    orThrow("Not removed", { outcome: "refused", status: 403, reasons: ["not yours"] }),
  ).toThrow("Not removed: not yours");
});
