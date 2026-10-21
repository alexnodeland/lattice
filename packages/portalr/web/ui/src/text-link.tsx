import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { ExternalLink } from "lucide-react";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";

/**
 * A link's variants (portalr ADR-0058): `inline`, in running text, in the working colour and
 * underlined; `subtle`, an id or a name in a table or a row, in the text's colour with a quiet
 * underline that takes the working colour when hovered; `nav`, one of a few places to go, in the
 * working colour and underlined only when hovered; `external`, inline, opening another site in a
 * new tab, which it says with a mark and in words.
 */
export type LinkVariant = "inline" | "subtle" | "nav" | "external";

const FOCUS =
  "outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus";

const UNDERLINE = "underline underline-offset-(--link-underline-offset)";

const LOOK: Record<LinkVariant, string> = {
  inline: `text-accent ${UNDERLINE}`,
  external: `inline-flex items-baseline gap-1 text-accent ${UNDERLINE}`,
  subtle: `text-fg ${UNDERLINE} decoration-edge hover:text-accent hover:decoration-accent`,
  nav: "font-medium text-accent underline-offset-(--link-underline-offset) hover:underline",
};

type Props = Omit<ComponentProps<"a">, "className"> & {
  /** What to render as the link, such as the router's own: an `<a>` without one. */
  render?: ReactElement;
  variant?: LinkVariant;
  className?: string;
};

/** A link, in one of the kit's variants; a router's link renders through `render`. */
export function TextLink({ render, variant = "inline", className, children, ...props }: Props) {
  const external = variant === "external";
  const content: ReactNode = external ? (
    <>
      {children}
      <Icon icon={ExternalLink} className="size-3.5 self-center" />
      <span className="sr-only">(opens in a new tab)</span>
    </>
  ) : (
    children
  );
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(LOOK[variant], FOCUS, className),
        ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}),
        children: content,
      },
      props,
    ),
  });
}
