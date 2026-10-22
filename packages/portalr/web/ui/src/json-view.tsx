import { cn } from "./cn";
import { CopyButton } from "./copy-button";
import { Disclosure } from "./disclosure";
import { isObject } from "./json";
import { ScrollRegion } from "./scroll-region";

/** A string longer than this, or with a line break in it, is shown as a block of its own. */
const LONG_STRING = 80;

/** The most keys or items a level shows; the rest are counted, and copied with the rest. */
export const MOST_ENTRIES = 100;

/** How deep a tree opens at first: deeper objects and lists are folded, to open on asking. */
const OPEN_DEPTH = 2;

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** A value, as a reader reads it: a string as its text, a number or a word as written. */
function Value({ value, depth }: { value: unknown; depth: number }) {
  if (typeof value === "string") {
    return value.includes("\n") || value.length > LONG_STRING ? (
      <pre className="m-0 mt-1 whitespace-pre-wrap break-words rounded-sm border border-line bg-surface px-2 py-1 font-mono text-fg text-xs">
        {value}
      </pre>
    ) : (
      <span className="break-words font-mono text-[var(--code-token-string)]">"{value}"</span>
    );
  }
  if (Array.isArray(value) || isObject(value)) {
    return <Branch value={value} depth={depth} />;
  }
  return (
    <span className="font-mono text-[var(--code-token-constant)]">{JSON.stringify(value)}</span>
  );
}

/** An object's keys, or a list's items, each with its value; folded past `OPEN_DEPTH`. */
function Branch({
  value,
  depth,
}: {
  value: readonly unknown[] | Readonly<Record<string, unknown>>;
  depth: number;
}) {
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((item, at) => [String(at), item])
    : Object.entries(value);
  const said = Array.isArray(value)
    ? count(entries.length, "item", "items")
    : count(entries.length, "key", "keys");
  if (entries.length === 0) {
    return <span className="font-mono text-muted">{Array.isArray(value) ? "[]" : "{}"}</span>;
  }
  const list = (
    <dl className={cn("m-0 flex flex-col gap-1", depth > 0 && "border-line border-s ps-3")}>
      {entries.slice(0, MOST_ENTRIES).map(([key, item]) => (
        <div key={key} className="min-w-0">
          <dt className="inline font-mono text-muted">{Array.isArray(value) ? `${key}.` : key}</dt>{" "}
          <dd className="m-0 inline">
            <Value value={item} depth={depth + 1} />
          </dd>
        </div>
      ))}
      {entries.length > MOST_ENTRIES && (
        <div className="text-muted text-xs">
          And {entries.length - MOST_ENTRIES} more, in what Copy copies.
        </div>
      )}
    </dl>
  );
  if (depth === 0) {
    return list;
  }
  return (
    <Disclosure
      summary={said}
      defaultOpen={depth < OPEN_DEPTH}
      className="inline-block w-full align-top"
      triggerClassName="w-fit text-xs"
      panelClassName="data-open:pt-0"
    >
      {list}
    </Disclosure>
  );
}

/**
 * JSON, as a reader reads it rather than as it is escaped (portalr ADR-0054): an object's keys,
 * each beside its value, a long string or one with line breaks as a block of its text, and a
 * nested object or list folded past the second level; in a region of its own height at most,
 * which scrolls, with Copy, which copies the JSON as it is.
 */
export function JsonView({ data, name = "JSON" }: { data: unknown; name?: string }) {
  return (
    <div className="flex min-w-0 flex-col rounded-(--code-block-radius) border border-line bg-paper">
      <div className="flex items-center justify-between gap-2 border-line border-b py-1 ps-3 pe-1">
        <span className="font-mono text-muted text-xs">json</span>
        <CopyButton text={JSON.stringify(data, null, 2)} what={`the ${name}`} />
      </div>
      <ScrollRegion
        aria-label={name}
        className="max-h-[32rem] overflow-y-auto px-3 py-2 text-fg text-sm -outline-offset-(--focus-offset)"
      >
        <Value value={data} depth={0} />
      </ScrollRegion>
    </div>
  );
}
