import { Square, SquareCheck } from "lucide-react";
import {
  type ComponentProps,
  createContext,
  type ReactNode,
  useContext,
  useId,
  useMemo,
} from "react";
import type { Options as Schema } from "rehype-sanitize";
import {
  type Components,
  defaultRehypePlugins,
  defaultRemarkPlugins,
  type ExtraProps,
  Streamdown,
  useIsCodeFenceIncomplete,
} from "streamdown";
import { useAddons } from "./addons";
import { Alert, type AlertTone } from "./alert";
import { CALLOUTS, type Callout, isCallout, remarkCallouts } from "./callouts";
import { cn } from "./cn";
import { CodeBlock } from "./code-block";
import { useHighlighted } from "./highlighting";
import { Icon } from "./icon";
import { useOnDemand } from "./on-demand";
import { ScrollRegion } from "./scroll-region";
import { linkLook } from "./text-link";

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
 * How unfinished Markdown is completed as it streams: as Streamdown does, but for block math, so a
 * formula still arriving isn't closed early and drawn half-written; it shows as its source until
 * it reads as a formula.
 */
const REMEND = { katex: false } as const;

/** Whether a message holds math: a `$$`, or a `math` fence. */
const HOLDS_MATH = /\$\$|^ {0,3}(?:`{3,}|~{3,})[ \t]*math\b/m;

/** Math's syntax alone, which shows each formula as its source while math is off. */
const loadMathSyntax = () =>
  import("./on-demand/math-syntax").then((math) => math.remarkMathSyntax);

/** Math's plugin for Streamdown, its syntax and its drawing, while math is on. */
const loadMath = () => import("./on-demand/math").then((math) => math.PLUGINS);

/** Whether the Markdown around is still streaming, so a formula still arriving isn't an error yet. */
const Streaming = createContext(false);

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

/** The add-ons whose fences show as their source, with their quiet lines: off, or not drawn yet. */
const UNDRAWN: ReadonlyMap<string, Record<"off" | "on", string>> = new Map([
  [
    "mermaid",
    {
      off: "Diagrams are off here: this is the diagram's source.",
      on: "Diagrams can't be drawn yet: this is the diagram's source.",
    },
  ],
]);

/** A diagram's fence, as its source with its quiet line. */
function Diagram({ code, language }: { code: string; language: string }) {
  const { mermaid } = useAddons();
  return (
    <CodeBlock
      code={code}
      language={language}
      note={UNDRAWN.get(language)?.[mermaid ? "on" : "off"]}
    />
  );
}

/**
 * A formula that reached `Markdown` as code: math is off, or still loading, or KaTeX couldn't read
 * it. Still arriving, it is its source, quietly, until it reads as a formula.
 */
function Formula({ code }: { code: string }) {
  const { math } = useAddons();
  const loaded = useOnDemand(loadMath, math);
  const streaming = useContext(Streaming);
  if (math && streaming) {
    return (
      <p className="whitespace-pre-wrap font-mono text-muted text-sm [font-variant-ligatures:none]">
        {code}
      </p>
    );
  }
  let note: string | undefined;
  if (!math) {
    note = "Math is off here: this is the formula's source.";
  } else if (loaded) {
    note = "This formula couldn't be drawn: this is its source.";
  }
  return <CodeBlock code={code} language="math" note={note} />;
}

/** Code, highlighted in a language `ui` highlights, a line at a time while it streams. */
function Highlightable({ code, language }: { code: string; language: string }) {
  const arriving = useIsCodeFenceIncomplete();
  const drawn = useHighlighted(code, language, !arriving);
  return (
    <CodeBlock code={code} language={language}>
      {drawn}
    </CodeBlock>
  );
}

/** A fence's language, from the class Markdown gives its code. */
const LANGUAGE = /(?:^|\s)language-(\S+)/;

/** A fenced block, which Streamdown hands `code` alone; inline code is `inlineCode`'s. */
function Fenced({ className, children }: { className?: string | undefined; children?: ReactNode }) {
  const language = LANGUAGE.exec(className ?? "")?.[1] ?? "";
  // Markdown closes a block's code with a line end, which isn't the code's.
  const code = typeof children === "string" ? children.replace(/\n$/, "") : "";
  if (language === "math") {
    return <Formula code={code} />;
  }
  if (UNDRAWN.has(language)) {
    return <Diagram code={code} language={language} />;
  }
  return <Highlightable code={code} language={language} />;
}

/** Inline code; a formula within a line that isn't drawn shows as its source, `$$` and all. */
function InlineCode({
  className,
  children,
}: {
  className?: string | undefined;
  children?: ReactNode;
}) {
  const formula = className?.split(" ").includes("language-math");
  return (
    <code className="rounded-(--code-inline-radius) bg-paper px-(--code-inline-pad-x) py-(--code-inline-pad-y) font-mono text-fg text-sm [font-variant-ligatures:none]">
      {formula ? ["$$", children, "$$"] : children}
    </code>
  );
}

/** A message's link: the kit's inline look, its ring and its feedback (portalr ADR-0059). */
const link = linkLook("inline");

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
  inlineCode: ({ className, children }) => (
    <InlineCode className={className}>{children}</InlineCode>
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
 * its callouts, with code blocks of `ui`'s own, and the add-ons the workspace's integrations allow.
 */
export function Markdown({ children, streaming = false, className }: Props) {
  const addons = useAddons();
  const math = HOLDS_MATH.test(children);
  const plugins = useOnDemand(loadMath, math && addons.math);
  const syntax = useOnDemand(loadMathSyntax, math && !addons.math);
  const remark = useMemo(() => (syntax ? [...REMARK, syntax] : REMARK), [syntax]);
  // Each Markdown's footnotes have ids of their own, so two messages' first footnotes don't share
  // one: React's id for this one, in letters and digits, which an `href` keeps as they are.
  const id = useId().replace(/[^A-Za-z0-9]/g, "");
  const footnotes = useMemo(() => ({ clobberPrefix: `md${id}-` }), [id]);
  return (
    <Streaming value={streaming}>
      <Streamdown
        className={cn("flex flex-col gap-2 text-fg text-sm", className)}
        mode={streaming ? "streaming" : "static"}
        isAnimating={streaming}
        remarkPlugins={remark}
        {...(plugins && { plugins })}
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
    </Streaming>
  );
}
