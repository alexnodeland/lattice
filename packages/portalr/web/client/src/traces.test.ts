import { expect, test } from "vitest";
import { CONTENT, kindOf, outline, said, type Trace } from "./traces";

const span = (
  id: string,
  parent: string | null,
  start: number,
  end: number,
  attributes: Trace["spans"][number]["attributes"] = {},
  rest: Partial<Trace["spans"][number]> = {},
): Trace["spans"][number] => ({
  span_id: id,
  parent_id: parent,
  name: `span ${id}`,
  start_ns: start * 1_000_000,
  end_ns: end * 1_000_000,
  attributes,
  error: false,
  withheld: [],
  ...rest,
});

const trace = (...spans: Trace["spans"]): Trace => ({ trace_id: "t".repeat(32), spans });

test("spans are in tree order, each parent before its children, children by start", () => {
  const { rows, duration } = outline(
    trace(
      span("c", "a", 30, 40),
      span("b", "a", 10, 20),
      span("a", null, 0, 50),
      span("d", "b", 12, 15),
      span("z", null, 60, 70),
    ),
  );
  expect(rows.map((row) => [row.id, row.depth])).toEqual([
    ["a", 0],
    ["b", 1],
    ["d", 2],
    ["c", 1],
    ["z", 0],
  ]);
  expect(rows.map((row) => row.parent)).toEqual([true, true, false, false, false]);
  expect(duration).toBe(70);
  expect(rows[1]).toMatchObject({ offset: 10, duration: 10, parentId: "a" });
});

test("a span whose parent isn't there, or a cycle of spans, is shown, not lost", () => {
  const orphan = outline(trace(span("o", "gone", 0, 1), span("p", null, 2, 3)));
  expect(orphan.rows.map((row) => [row.id, row.depth])).toEqual([
    ["o", 0],
    ["p", 0],
  ]);
  const cycle = outline(trace(span("x", "y", 0, 1), span("y", "x", 1, 2)));
  expect(cycle.rows.map((row) => row.id).sort()).toEqual(["x", "y"]);
  expect(outline(trace())).toEqual({ rows: [], duration: 0 });
});

test("a span is what its GenAI operation says, or what else it carries", () => {
  expect(kindOf({ "gen_ai.operation.name": "invoke_workflow" })).toBe("workflow");
  expect(kindOf({ "gen_ai.operation.name": "invoke_agent" })).toBe("agent");
  expect(kindOf({ "gen_ai.operation.name": "chat" })).toBe("llm");
  expect(kindOf({ "gen_ai.operation.name": "execute_tool" })).toBe("tool");
  expect(kindOf({ "http.request.method": "POST" })).toBe("http");
  expect(kindOf({ "db.system": "postgresql" })).toBe("database");
  expect(kindOf({ "gen_ai.operation.name": "toString" })).toBe("other");
  expect(kindOf({})).toBe("other");
});

test("a span's model, tool, tokens, error and what it withheld are read from it", () => {
  const { rows } = outline(
    trace(
      span(
        "1",
        null,
        0,
        5,
        {
          "gen_ai.operation.name": "chat",
          "gen_ai.request.model": "claude",
          "gen_ai.usage.input_tokens": 120,
          "gen_ai.usage.output_tokens": 30,
        },
        { error: true, withheld: ["gen_ai.input.messages"] },
      ),
      span("2", "1", 1, 2, { "gen_ai.tool.name": "publish", "gen_ai.response.model": "r" }),
      span("3", "1", 2, 3, { "gen_ai.usage.output_tokens": 4 }),
    ),
  );
  expect(rows[0]).toMatchObject({
    model: "claude",
    error: true,
    tokens: { input: 120, output: 30 },
    withheld: ["gen_ai.input.messages"],
  });
  expect(rows[1]).toMatchObject({ tool: "publish", model: "r", tokens: null, said: [] });
  expect(rows[2]?.tokens).toEqual({ input: null, output: 4 });
});

test("what was said is each part, labelled, its JSON indented, and nothing if it wasn't read", () => {
  expect(said({})).toEqual([]);
  expect(
    said({
      "gen_ai.input.messages": '[{"role":"user"}]',
      "gen_ai.output.messages": "not json",
      "gen_ai.tool.call.result": 3,
    }),
  ).toEqual([
    { label: "Prompt", text: '[\n  {\n    "role": "user"\n  }\n]' },
    { label: "Completion", text: "not json" },
  ]);
  expect(CONTENT).toContain("gen_ai.system_instructions");
});
