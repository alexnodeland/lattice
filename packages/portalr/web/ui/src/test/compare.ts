import type { Change, Granularity } from "@portalr/client";

/** Text cut as `client`'s `changes` cuts it: whole lines, or words and the spaces between. */
const pieces = (text: string, by: Granularity) =>
  (by === "lines" ? text.match(/[^\n]*\n|[^\n]+/g) : text.match(/\s+|\S+/g)) ?? [];

/**
 * What `client`'s `changes` gives, for a test's small texts: the longest common run of pieces kept,
 * the rest removed or added, with each run of a kind joined. `ui` imports `client`'s types alone
 * (portalr ADR-0015), so its tests compare with this rather than with jsdiff.
 */
export function compare(before: string, after: string, by: Granularity): Change[] {
  const a = pieces(before, by);
  const b = pieces(after, by);
  const longest = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      const row = longest[i] as number[];
      row[j] =
        a[i] === b[j]
          ? ((longest[i + 1] as number[])[j + 1] as number) + 1
          : Math.max((longest[i + 1] as number[])[j] as number, row[j + 1] as number);
    }
  }
  const changes: Change[] = [];
  const push = (kind: Change["kind"], text: string) => {
    const last = changes.at(-1);
    if (last?.kind === kind) {
      changes[changes.length - 1] = { kind, text: last.text + text };
    } else {
      changes.push({ kind, text });
    }
  };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      push("same", a[i] as string);
      i += 1;
      j += 1;
    } else if (
      j < b.length &&
      (i === a.length ||
        ((longest[i] as number[])[j + 1] as number) >= ((longest[i + 1] as number[])[j] as number))
    ) {
      push("added", b[j] as string);
      j += 1;
    } else {
      push("removed", a[i] as string);
      i += 1;
    }
  }
  // As jsdiff does, what was removed comes before what took its place.
  for (let at = 1; at < changes.length; at += 1) {
    const [first, second] = [changes[at - 1] as Change, changes[at] as Change];
    if (first.kind === "added" && second.kind === "removed") {
      changes[at - 1] = second;
      changes[at] = first;
    }
  }
  return changes;
}
