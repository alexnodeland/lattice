import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { expect, expectTypeOf, test } from "vitest";
import { bareRefs, commands, GENERATED, generate } from "../scripts/generate";
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
