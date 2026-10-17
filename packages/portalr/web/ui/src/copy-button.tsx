import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "./button";
import { Icon } from "./icon";

/** How long "Copied" shows before the button offers to copy again. */
const SHOWN_MS = 2000;

/**
 * Copy `text` as it is: a small button whose words say it (`Copy`, then `Copied` or `Couldn't
 * copy`), named in full for assistive technology by `label`, with what happened said politely. Where
 * the page has no clipboard, as outside a secure context, it says it couldn't.
 */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState<boolean | null>(null);
  useEffect(() => {
    if (copied === null) {
      return;
    }
    const again = setTimeout(() => setCopied(null), SHOWN_MS);
    return () => clearTimeout(again);
  }, [copied]);
  const said = copied === null ? "" : copied ? "Copied" : "Couldn't copy";
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        aria-label={label}
        onClick={() => {
          Promise.resolve()
            .then(() => navigator.clipboard.writeText(text))
            .then(() => setCopied(true))
            .catch(() => setCopied(false));
        }}
      >
        <Icon icon={copied ? Check : Copy} className="size-3.5" />
        {said || "Copy"}
      </Button>
      <span role="status" className="sr-only">
        {said}
      </span>
    </>
  );
}
