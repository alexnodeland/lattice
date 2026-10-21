import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { ExternalLink } from "lucide-react";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";

/**
 * A link's variants (portalr ADR-0059):
 * - `inline`, in running text: the working colour, underlined.
 * - `subtle`, an id or a name standing alone, in a table's cell, a row or a breadcrumb: the text's
 *   colour, a quiet underline that takes the working colour when hovered. Never in running text,
 *   where only its underline would tell it from the words around it.
 * - `nav`, one of a few places to go: the working colour, underlined only when hovered.
 * - `external`, inline, opening another site in a new tab, which a mark and words say.
 */
export type LinkVariant = "inline" | "subtle" | "nav" | "external";

const FOCUS =
  "outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus";

const UNDERLINE = "underline underline-offset-(--link-underline-offset)";

const LOOK: Record<LinkVariant, string> = {
  inline: `text-accent ${UNDERLINE}`,
  external: `text-accent ${UNDERLINE}`,
  subtle: `text-fg ${UNDERLINE} decoration-edge hover:text-accent hover:decoration-accent`,
  nav: "font-medium text-accent text-sm underline-offset-(--link-underline-offset) hover:underline",
};

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
          icon={ExternalLink}
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
      className: cn(LOOK[variant], FOCUS, className),
      children: external ? withMark(children) : children,
      ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}),
    }),
  });
}
