import { Square, SquareCheck } from "lucide-react";
import { type ComponentProps, type ReactNode, useId, useMemo } from "react";
import type { Options as Schema } from "rehype-sanitize";
import {
  type Components,
  defaultRehypePlugins,
  defaultRemarkPlugins,
  type ExtraProps,
  Streamdown,
} from "streamdown";
import { type Addons, useAddons } from "./addons";
import { Alert, type AlertTone } from "./alert";
import { CALLOUTS, type Callout, isCallout, remarkCallouts } from "./callouts";
import { cn } from "./cn";
import { CodeBlock } from "./code-block";
import { Icon } from "./icon";
import { ScrollRegion } from "./scroll-region";

type Pluggable = NonNullable<ComponentProps<typeof Streamdown>["rehypePlugins"]>[number];

/** Streamdown's sanitizer, and its schema, which ours extends. */
const [sanitize, streamdownSchema] = defaultRehypePlugins.sanitize as [Pluggable, Schema];

/**
 * What may pass the sanitizer: Streamdown's schema, and a callout, which `remarkCallouts` makes,
 * as an `aside` of a known kind. No HTML a message holds reaches it (`skipHtml`).
 */
const SCHEMA: Schema = {
  ...streamdownSchema,
  tagNames: [...(streamdownSchema.tagNames ?? []), "aside"],
  attributes: { ...streamdownSchema.attributes, aside: [["dataCallout", ...CALLOUTS]] },
};

/**
 * Sanitizing alone: no `rehype-raw`, which Streamdown adds to pass HTML through, and no
 * `rehype-harden`, whose rules the components below keep instead. Built once, since Streamdown
 * re-renders a block whose plugins change, which every new array would be.
 */
const REHYPE: Pluggable[] = [[sanitize, SCHEMA] as Pluggable];

/** GitHub's Markdown, as Streamdown parses it, and its callouts. */
const REMARK: Pluggable[] = [...Object.values(defaultRemarkPlugins), remarkCallouts];

/**
 * How unfinished Markdown is completed as it streams: as Streamdown does, but for block math, which
 * nothing draws yet, so a `$$` mid-stream stays as it was written rather than being closed.
 */
const REMEND = { katex: false } as const;

/** The protocols a link may use: the web, and mail. */
const LINKED = new Set(["https:", "http:", "mailto:"]);

/**
 * Where a link may go, from this page at `origin` (portalr ADR-0015): a place on the page, this
 * application, the web or mail. Anything else, such as `javascript:`, `data:`, `xmpp:` or the
 * `streamdown:incomplete-link` a link still streaming is given, is no link at all.
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

/** How each callout shows: its alert's tone, and its word, which always shows with it. */
const CALLOUT: Record<Callout, { readonly tone: AlertTone; readonly word: string }> = {
  note: { tone: "info", word: "Note" },
  tip: { tone: "info", word: "Tip" },
  important: { tone: "info", word: "Important" },
  warning: { tone: "warn", word: "Warning" },
  caution: { tone: "error", word: "Caution" },
};

/** The add-on whose fences each language is, which shows a fence as its source while it can't draw. */
const ADDON_OF: ReadonlyMap<string, keyof Addons> = new Map([["mermaid", "mermaid"]]);

/** The quiet line under an add-on's fence that shows as its source: off, or on but not drawn yet. */
const UNDRAWN: Record<keyof Addons, Record<"off" | "on", string>> = {
  mermaid: {
    off: "Diagrams are off here: this is the diagram's source.",
    on: "Diagrams can't be drawn yet: this is the diagram's source.",
  },
};

/** A fence's language, from the class Markdown gives its code. */
const LANGUAGE = /(?:^|\s)language-(\S+)/;

/** A fenced block, which Streamdown hands `code` alone; inline code is `inlineCode`'s. */
function Fenced({ className, children }: { className?: string | undefined; children?: ReactNode }) {
  const addons = useAddons();
  const language = LANGUAGE.exec(className ?? "")?.[1] ?? "";
  const addon = ADDON_OF.get(language);
  // Markdown closes a block's code with a line end, which isn't the code's.
  const code = typeof children === "string" ? children.replace(/\n$/, "") : "";
  return (
    <CodeBlock
      code={code}
      language={language}
      note={addon && UNDRAWN[addon][addons[addon] ? "on" : "off"]}
    />
  );
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
  // A task's box can't be ticked here: it is a drawing, and its state is said in words.
  input: ({ checked }) => (
    <>
      <Icon
        icon={checked ? SquareCheck : Square}
        className="mr-1.5 inline size-4 align-text-bottom"
      />
      <span className="sr-only">{checked ? "Done:" : "To do:"}</span>
    </>
  ),
  code: ({ className, children }) => <Fenced className={className}>{children}</Fenced>,
  inlineCode: ({ children }) => (
    <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-fg text-sm [font-variant-ligatures:none]">
      {children}
    </code>
  ),
  table: ({ children }) => (
    <ScrollRegion aria-label="Table" className="rounded-md border border-line">
      <table className="w-full border-collapse text-sm">{children}</table>
    </ScrollRegion>
  ),
  thead: ({ children }) => <thead className="bg-paper">{children}</thead>,
  aside: ({ node, children }: ExtraProps & { children?: ReactNode }) => {
    // The sanitizer lets an aside through with a callout's kind alone.
    const kind = node?.properties.dataCallout;
    const { tone, word } = CALLOUT[isCallout(kind) ? kind : "note"];
    return (
      <Alert tone={tone} live={false}>
        <div className="flex flex-col gap-1">
          <p className="font-semibold">{word}</p>
          {children}
        </div>
      </Alert>
    );
  },
};

type Props = {
  children: string;
  /** Whether the text is still arriving: unfinished Markdown is completed as it streams. */
  streaming?: boolean;
  className?: string;
};

/**
 * Markdown, as an agent writes it, rendered as it streams, through Streamdown: GitHub's Markdown and
 * its callouts, with code blocks of `ui`'s own, and the add-ons `AddonsProvider` allows.
 */
export function Markdown({ children, streaming = false, className }: Props) {
  // Each Markdown's footnotes have ids of their own, so two messages' first footnotes don't share
  // one: React's id for this one, in letters and digits, which an `href` keeps as they are.
  const id = useId().replace(/[^A-Za-z0-9]/g, "");
  const footnotes = useMemo(() => ({ clobberPrefix: `md${id}-` }), [id]);
  return (
    <Streamdown
      className={cn("flex flex-col gap-2 text-fg text-sm", className)}
      mode={streaming ? "streaming" : "static"}
      isAnimating={streaming}
      remarkPlugins={REMARK}
      rehypePlugins={REHYPE}
      remarkRehypeOptions={footnotes}
      remend={REMEND}
      components={COMPONENTS}
      skipHtml
      linkSafety={{ enabled: false }}
      controls={false}
    >
      {children}
    </Streamdown>
  );
}
