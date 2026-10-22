import type { ComponentProps } from "react";
import { Heading } from "./heading";

/**
 * A section's heading, under the page's one: the same size and weight wherever a page has one. A
 * form that opens on it may focus it, with `tabIndex={-1}` and a `ref`, and no ring is drawn.
 */
export function SectionTitle(props: Omit<ComponentProps<"h2">, "className">) {
  return <Heading level={2} look="section" {...props} />;
}
