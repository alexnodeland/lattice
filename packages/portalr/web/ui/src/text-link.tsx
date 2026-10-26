import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { FEEDBACK, RING } from "./states";

/**
 * A link's variants (portalr ADR-0059, ADR-0080):
 * - `inline`, in running text: the working colour, with a quiet rule under it that takes the
 *   working colour when hovered, never the browser's own underline.
 * - `subtle`, an id or a name standing alone, in a table's cell: the text's colour and weight,
 *   the working colour when hovered or reached. Never in running text, where nothing would tell
 *   it from the words around it.
 * - `external`, inline, opening another site in a new tab, which a mark and words say.
 * A way on that is an action, "All threads", is a `ButtonLink`; a list's row is its own
 * component; the places above a page are `Breadcrumbs`.
 */
export type LinkVariant = "inline" | "subtle" | "external";

const UNDERLINE =
  "underline decoration-edge underline-offset-(--link-underline-offset) hover:decoration-accent";

const LOOK: Record<LinkVariant, string> = {
  inline: `text-accent ${UNDERLINE}`,
  external: `text-accent ${UNDERLINE}`,
  subtle: "font-semibold text-fg hover:text-accent focus-visible:text-accent",
};

/** A link's look, with the ring and the feedback, for a link the kit doesn't render itself, such as Markdown's. */
export function linkLook(variant: LinkVariant) {
  return cn(LOOK[variant], RING, FEEDBACK);
}

type Props = Omit<ComponentProps<"a">, "className"> & {
  /**
   * What to render as the link, such as the router's own: an `<a>` without one. Its children are
   * replaced by the link's own.
   */
  render?: ReactElement;
  variant?: LinkVariant;
  className?: string;
};

/**
 * An external link's words with its mark, which stays on the line with the last word: in words, the
 * last word and the mark are kept together; otherwise the mark follows what was given.
 */
function withMark(children: ReactNode) {
  const text = typeof children === "string" ? children.trimEnd() : null;
  const words = text === null ? -1 : text.lastIndexOf(" ");
  const head = text === null || words < 0 ? null : text.slice(0, words + 1);
  const tail = text === null ? children : text.slice(words + 1);
  return (
    <>
      {head}
      <span className="whitespace-nowrap">
        {tail}
        <Icon
          icon={glyphs.externalLink}
          className="ms-(--link-mark-gap) inline size-(--link-mark-size) align-baseline"
        />
      </span>
      <span className="sr-only"> (opens in a new tab)</span>
    </>
  );
}

/**
 * A link, in one of the kit's variants; a router's link renders through `render`. An external
 * link's `target` and `rel` are its own, after the caller's, so a caller can't weaken them.
 */
export function TextLink({ render, variant = "inline", className, children, ...props }: Props) {
  const external = variant === "external";
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(props, {
      className: cn(linkLook(variant), className),
      children: external ? withMark(children) : children,
      ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}),
    }),
  });
}
