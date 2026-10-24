import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "./button";
import { Icon } from "./icon";

/** How long "Copied" shows before the button offers to copy again. */
const SHOWN_MS = 2000;

/**
 * Copy `text` as it is: a small button whose words say it (`Copy`, then `Copied` or `Couldn't
 * copy`), named in full with `what` (`Copy the ts code`), so its name always holds its words, with
 * what happened said politely each time. Where the page has no clipboard, as outside a secure
 * context, it says it couldn't. Where many sit together, as in a table's rows, `onSaid` takes
 * what it would say, for the one status their page keeps, and the button keeps none of its own.
 */
export function CopyButton({
  text,
  what,
  onSaid,
}: {
  text: string;
  what: string;
  onSaid?: ((said: string) => void) | undefined;
}) {
  // Each copy is a new object, so a second within the time is said again, and shown for the time.
  const [copy, setCopy] = useState<{ readonly said: string } | null>(null);
  useEffect(() => {
    if (copy === null) {
      return;
    }
    const again = setTimeout(() => setCopy(null), SHOWN_MS);
    return () => clearTimeout(again);
  }, [copy]);
  const said = copy?.said ?? "Copy";
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        aria-label={`${said} ${what}`}
        onClick={() => {
          // From a promise, so a page with no `navigator.clipboard` at all is caught as well.
          Promise.resolve()
            .then(() => navigator.clipboard.writeText(text))
            .then(
              () => "Copied",
              () => "Couldn't copy",
            )
            .then((done) => {
              setCopy({ said: done });
              onSaid?.(`${done} ${what}`);
            });
        }}
      >
        <Icon icon={copy?.said === "Copied" ? Check : Copy} className="size-3.5" />
        {said}
      </Button>
      {onSaid === undefined && (
        <span role="status" className="sr-only">
          {copy && `${copy.said} ${what}`}
        </span>
      )}
    </>
  );
}
