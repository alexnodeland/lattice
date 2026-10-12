import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { expect, test } from "vitest";
import { bareRefs, GENERATED, generate } from "../scripts/generate";

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
