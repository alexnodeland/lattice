import type { ComponentProps } from "react";
import { defaultRehypePlugins, Streamdown } from "streamdown";
import { cn } from "./cn";

type Pluggable = NonNullable<ComponentProps<typeof Streamdown>["rehypePlugins"]>[number];

const [harden] = defaultRehypePlugins.harden as [Pluggable, unknown];

/**
 * What Markdown may render (portalr ADR-0015): no raw HTML, which Streamdown passes through by
 * default; links on the web and to mail alone; images from this origin alone, as the router's
 * Content-Security-Policy allows, so any other shows as blocked.
 */
function rehypePlugins(origin: string): Pluggable[] {
  return [
    defaultRehypePlugins.sanitize as Pluggable,
    [
      harden,
      {
        allowedProtocols: ["https", "http", "mailto"],
        allowedLinkPrefixes: ["*"],
        allowedImagePrefixes: [origin],
        defaultOrigin: origin,
        allowDataImages: false,
      },
    ] as Pluggable,
  ];
}

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
      rehypePlugins={rehypePlugins(location.origin)}
      skipHtml
      linkSafety={{ enabled: false }}
      controls={false}
    >
      {children}
    </Streamdown>
  );
}
