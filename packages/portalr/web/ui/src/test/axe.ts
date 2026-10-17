import axe from "axe-core";

/** What axe finds wrong within an element, as `rule: where`, one line each; none is an empty list. */
export async function axeViolations(within: Element): Promise<string[]> {
  const { violations } = await axe.run(within, { resultTypes: ["violations"] });
  return violations.flatMap((violation) =>
    violation.nodes.map((node) => `${violation.id}: ${node.target.join(" ")}`),
  );
}
