/**
 * What an agent's proposal on a native file does, from the commands it was made by (portalr
 * ADR-0089, native files ADR-0020), as a tool call's fold shows a run's calls (ADR-0053): a line
 * in words, the first level, which opens to each change, the second, each to its arguments, and
 * to the commands themselves, the last. Beneath the line on a desktop; on a phone, a sheet whose
 * list goes on to a change, and Back to the list, the focus following. A proposal made by no
 * commands, as a person's check-in kept as one, says nothing here.
 */

import type { FilesApi } from "@portalr/client";
import { Button, Dialog, Disclosure, glyphs, Icon, JsonView, usePhone } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import type { Place } from "./check-out";

type Said = FilesApi.components["schemas"]["Described"];

/** A button laid out as a line of words: as wide as they are, wrapping, from the start. */
const ROW = "justify-start whitespace-normal px-0 text-start";

export function NativeChanges({ place, proposal }: { place: Place; proposal: string }) {
  const { context, tenant, workspace } = place;
  const { data: said } = useQuery(
    context.queries.files.proposedCommands(tenant, workspace, proposal),
  );
  const phone = usePhone();
  // How it is open, chosen at the tap from what the window is then: beneath, or a sheet.
  const [shown, setShown] = useState<"list" | "sheet" | null>(null);
  const line = useRef<HTMLButtonElement>(null);
  const list = useId();
  if (!said) {
    return null;
  }
  const sheet = (shown ?? (phone ? "sheet" : "list")) === "sheet";
  return (
    <>
      <Button
        ref={line}
        variant="ghost"
        aria-expanded={shown !== null}
        {...(sheet ? { "aria-haspopup": "dialog" as const } : { "aria-controls": list })}
        onClick={() => setShown(shown ? null : phone ? "sheet" : "list")}
        className={`${ROW} self-start font-semibold`}
      >
        <span>{said.summary}</span>
        <Icon
          icon={glyphs.chevronRight}
          className={`size-3.5 shrink-0 text-muted rtl:-scale-x-100 ${shown === "list" ? "rotate-90" : ""}`}
        />
      </Button>
      {shown === "list" && (
        <div id={list} className="flex flex-col gap-2 text-sm">
          <ol aria-label="Its changes" className="ms-1.5 flex flex-col border-line border-s ps-2">
            {said.items.map((item, at) => (
              <li key={at}>
                <Disclosure look="block" summary={item.text}>
                  <Args item={item} />
                </Disclosure>
              </li>
            ))}
          </ol>
          <Rest said={said} />
        </div>
      )}
      <ChangesSheet
        said={said}
        open={shown === "sheet"}
        onOpenChange={(open) => setShown(open ? "sheet" : null)}
        line={line}
      />
    </>
  );
}

/** A change's command, its arguments, to copy. */
const Args = ({ item }: { item: Said["items"][number] }) => (
  <JsonView data={item.args} name={`arguments of ${item.name}`} />
);

/** How many changes aren't listed, and the commands themselves, the last level. */
function Rest({ said }: { said: Said }) {
  const more = said.total - said.items.length;
  return (
    <>
      {more > 0 && <p className="text-muted">And {more.toLocaleString()} more.</p>}
      <Disclosure summary="Its commands">
        <JsonView data={said.items.map(({ name, args }) => ({ name, args }))} name="commands" />
      </Disclosure>
    </>
  );
}

/** On a phone, a sheet: the changes, each going on to its arguments, and Back to the list. */
function ChangesSheet({
  said,
  open,
  onOpenChange,
  line,
}: {
  said: Said;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  line: React.RefObject<HTMLButtonElement | null>;
}) {
  const [chosen, setChosen] = useState<number | null>(null);
  // The change last opened, whose row takes the focus back from it.
  const [left, setLeft] = useState<number | null>(null);
  const item = chosen === null ? undefined : said.items[chosen];
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setChosen(null);
        setLeft(null);
        onOpenChange(next);
      }}
      title={said.summary}
      finalFocus={line}
    >
      {item ? (
        <div className="flex flex-col gap-3 text-sm">
          <Button
            variant="ghost"
            size="sm"
            className="self-start"
            // The focus moves with the reader: to Back, and from it to the change's row.
            autoFocus
            onClick={() => {
              setLeft(chosen);
              setChosen(null);
            }}
          >
            <Icon icon={glyphs.chevronLeft} className="size-3.5 rtl:-scale-x-100" />
            Back to the changes
          </Button>
          <p>{item.text}</p>
          <Args item={item} />
        </div>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <ol aria-label="Its changes" className="flex flex-col">
            {said.items.map((each, at) => (
              <li key={at}>
                <Button
                  variant="ghost"
                  autoFocus={at === left}
                  onClick={() => setChosen(at)}
                  className={`${ROW} min-h-11 w-full`}
                >
                  <span className="min-w-0 flex-1">{each.text}</span>
                  <Icon
                    icon={glyphs.chevronRight}
                    className="size-3.5 shrink-0 text-muted rtl:-scale-x-100"
                  />
                </Button>
              </li>
            ))}
          </ol>
          <Rest said={said} />
        </div>
      )}
    </Dialog>
  );
}
