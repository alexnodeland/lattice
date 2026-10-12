import type { ComponentProps } from "react";
import { type Components, defaultRehypePlugins, Streamdown } from "streamdown";
import { cn } from "./cn";

type Pluggable = NonNullable<ComponentProps<typeof Streamdown>["rehypePlugins"]>[number];

/**
 * Sanitizing alone: no `rehype-raw`, which Streamdown adds to pass HTML through, and no
 * `rehype-harden`, whose rules the components below keep instead. Built once, since Streamdown
 * re-renders a block whose plugins change, which every new array would be.
 */
const REHYPE: Pluggable[] = [defaultRehypePlugins.sanitize as Pluggable];

/** The protocols a link may use: the web, and mail. */
const LINKED = new Set(["https:", "http:", "mailto:"]);

/**
 * Where a link may go, from this page at `origin` (portalr ADR-0015): a place on the page, this
 * application, the web or mail. Anything else, such as `javascript:`, `data:` or `xmpp:`, is no
 * link at all.
 */
export function linkTo(
  href: string | undefined,
  origin: string,
): { readonly href: string; readonly away: boolean } | null {
  if (!href) {
    return null;
  }
  if (href.startsWith("#")) {
    return { href, away: false };
  }
  let url: URL;
  try {
    url = new URL(href, origin);
  } catch {
    return null;
  }
  if (!LINKED.has(url.protocol)) {
    return null;
  }
  return { href: url.href, away: url.origin !== origin };
}

/** Whether an image may show: from this application alone, as its Content-Security-Policy says. */
export function showable(src: unknown, origin: string): string | null {
  if (typeof src !== "string" || !src) {
    return null;
  }
  try {
    const url = new URL(src, origin);
    return url.origin === origin ? url.href : null;
  } catch {
    return null;
  }
}

const link = "text-accent underline underline-offset-2";

const COMPONENTS: Components = {
  a: ({ href, children }) => {
    const target = linkTo(href, location.origin);
    if (target === null) {
      return <span>{children}</span>;
    }
    return target.away ? (
      <a href={target.href} className={link} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ) : (
      <a href={target.href} className={link}>
        {children}
      </a>
    );
  },
  img: ({ src, alt }) => {
    const shown = showable(src, location.origin);
    return shown === null ? (
      <span className="text-muted italic">Image blocked: {alt || "from another site"}</span>
    ) : (
      <img src={shown} alt={alt ?? ""} className="max-w-full rounded-md" />
    );
  },
  inlineCode: ({ children }) => (
    <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-fg text-sm">{children}</code>
  ),
  thead: ({ children }) => <thead className="bg-paper">{children}</thead>,
};

type Props = {
  children: string;
  /** Whether the text is still arriving: unfinished Markdown is completed as it streams. */
  streaming?: boolean;
  className?: string;
};

/** Markdown, as an agent writes it, rendered as it streams, through Streamdown. */
export function Markdown({ children, streaming = false, className }: Props) {
  return (
    <Streamdown
      className={cn("flex flex-col gap-2 text-fg text-sm", className)}
      mode={streaming ? "streaming" : "static"}
      isAnimating={streaming}
      rehypePlugins={REHYPE}
      components={COMPONENTS}
      skipHtml
      linkSafety={{ enabled: false }}
      controls={false}
    >
      {children}
    </Streamdown>
  );
}
