import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { expect, expectTypeOf, test } from "vitest";
import {
  bareRefs,
  called,
  calls,
  commands,
  GENERATED,
  generate,
  named,
  USED,
  used,
} from "../scripts/generate";
import { COMMANDS, type CommandName } from "./generated/commands";

// The types are the packages' committed documents, as openapi-typescript and
// json-schema-to-typescript write them: `moon run client:types` regenerates them.
test("the generated types match the committed documents", async () => {
  for (const [name, text] of Object.entries(await generate())) {
    expect(await readFile(join(GENERATED, name), "utf8"), name).toBe(text);
  }
});

test("a reference keeps its type when annotations sit beside it", () => {
  const annotated = { $ref: "#/$defs/JsonValue", default: null, deprecated: true, $comment: "x" };
  expect(bareRefs({ properties: { answer: annotated, list: [annotated] } })).toEqual({
    properties: { answer: { $ref: "#/$defs/JsonValue" }, list: [{ $ref: "#/$defs/JsonValue" }] },
  });
});

test("a reference with a constraint beside it fails, rather than becoming an object", () => {
  const constrained = { properties: { id: { $ref: "#/$defs/Id", minLength: 1 } } };
  expect(() => bareRefs(constrained)).toThrow("#/properties/id: a $ref with minLength beside it");
});

test("every command's name is a constant and a union, sorted, from the catalogs", () => {
  const catalog = (...names: string[]) =>
    JSON.stringify({ title: "x", commands: Object.fromEntries(names.map((n) => [n, {}])) });
  const text = commands([catalog("grantr.revoke_key", "grantr.add_member"), catalog("a.b")]);
  expect(text).toContain('export const COMMANDS = [\n  "a.b",\n  "grantr.add_member",\n');
  expect(text).toContain("export type CommandName = (typeof COMMANDS)[number];");
  expect(COMMANDS).toContain("artifactr.post_message");
  expect(new Set(COMMANDS).size).toBe(COMMANDS.length);
  // A name the catalogs declare is a `CommandName`; one they don't fails `tsc`.
  expectTypeOf<"grantr.revoke_key">().toExtend<CommandName>();
  expectTypeOf<"grantr.revoke_everything">().not.toExtend<CommandName>();
});

test("what each operation calls is its extension's command, a choice, none, or its frames", () => {
  expect(called("grantr.list_keys", "x")).toBe('"grantr.list_keys"');
  expect(called(["grantr.grant", "grantr.grant_on_tenant"], "x")).toBe(
    '"grantr.grant" | "grantr.grant_on_tenant"',
  );
  expect(called({ none: "config" }, "x")).toBe("null");
  expect(called({ frames: "command", none: { watch_run: "the stream's" } }, "x")).toBe('"frames"');
  expect(() => called(undefined, "grantr GET /keys")).toThrow(
    "grantr GET /keys: x-lattice-command is undefined",
  );
  const document = {
    paths: {
      "/keys": {
        parameters: [],
        get: { "x-lattice-command": "grantr.list_keys" },
        post: { "x-lattice-command": { none: "why" } },
      },
    },
  };
  expect(calls({ grantr: document })).toContain(
    '  grantr: {\n    "/keys": { get: "grantr.list_keys"; post: null; };\n  };\n',
  );
});

test("each request names its command before its path, or fails the manifest", () => {
  const source = `
    api.grantr.GET("grantr.list_keys", "/grantr/v1/tenants/{tenant}/keys", init);
    api.grantr.POST(
      kind === "tenant" ? "grantr.grant_on_tenant" : "grantr.grant",
      "/grantr/v1/tenants/{tenant}/grants",
    );
    api.grantr.DELETE("grantr.remove_member", \`/members/\${kind}/{member_id}\`);
    client.GET(null, "/portalr/config.json");
    api.artifactr.POST("frames", "/workspaces/{workspace_id}/commands", init);
  `;
  expect(named(source, "x.ts")).toEqual([
    "grantr.list_keys",
    "grantr.grant_on_tenant",
    "grantr.grant",
    "grantr.remove_member",
  ]);
  expect(() => named('api.grantr.GET(command, "/keys")', "y.ts")).toThrow(
    'y.ts: .GET(command, "/ names no command with a literal',
  );
});

// What portalr's UIs send over REST, read from their requests: `moon run client:types` rewrites it.
test("commands.used.json lists every command the UIs' requests name", async () => {
  expect(await readFile(USED, "utf8")).toBe(await used());
  const listed = JSON.parse(await readFile(USED, "utf8")) as string[];
  expect(listed).toContain("grantr.revoke_key");
  for (const name of listed) {
    expect(COMMANDS, name).toContain(name);
  }
});
