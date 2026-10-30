/**
 * The tools a run called, in its thread (portalr ADR-0053): each run of them one quiet line that
 * says what they did, opening to the calls, each to its detail, and that to its raw form.
 */

import { Button as BaseButton } from "@base-ui/react/button";
import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import type { Artifactr } from "@portalr/client";
import type { ReactNode } from "react";
import { type RefObject, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { CopyButton } from "./copy-button";
import { backdrop, popup } from "./dialog";
import { Disclosure } from "./disclosure";
import { keepTabWithin } from "./full-view";
import { Icon } from "./icon";
import { IconButton } from "./icon-button";
import { glyphs } from "./icons";
import { useRetrying } from "./on-demand";
import { ScrollRegion } from "./scroll-region";
import { SheetHandle, sheet, useSheet } from "./sheet";
import { RING } from "./states";
import { StatusBadge, type Tone } from "./status-badge";
import { callAbout, callLabel, foldSummary } from "./tool-fold";
import { phoneNow, usePhone } from "./touch";
import { TYPE } from "./type";

/** How a call is going, as a shape and a word, by the status its run recorded. */
const STATUS: Record<string, readonly [Tone, string, string]> = {
  // tone, the badge's word, and what the second part holds
  called: ["working", "Running", "Result"],
  ok: ["done", "Done", "Result"],
  error: ["failed", "Failed", "Error"],
  retry: ["retrying", "Refused", "Why it was refused"],
};

/** What the second part holds, in plain words. */
const PLAIN: Record<string, string> = { Result: "What it returned", Error: "Why it failed" };

/** The formatted view of a call's parts (portalr ADR-0083), loaded as a call is first opened. */
const loadJsonView = () => import("./on-demand/json-view");

type JsonView = Awaited<ReturnType<typeof loadJsonView>>;

/**
 * A part of a call: its name, a way to copy what is shown, and its value, scrolled where it is
 * long, which the keyboard reaches and scrolls too: JSON indented, or, once `view` has loaded,
 * formatted, with a toggle to the raw view. A value the run cut short, at its limit, says so.
 */
function Part({
  name,
  label = name,
  tool,
  text,
  cut,
  view,
}: {
  name: string;
  /** What it is called where it is shown, in plain words: "What it was asked". */
  label?: string;
  tool: string;
  /** The value, as the run recorded it. */
  text: string;
  cut: boolean;
  view: JsonView | null;
}) {
  const what = `the ${name.toLowerCase()} of ${tool}`;
  // As recorded until the formatted view loads, which indents it; no arguments are `{}`.
  const shown = text || (name === "Arguments" ? "{}" : "");
  const region = (children: ReactNode) => (
    <ScrollRegion
      aria-label={what.charAt(0).toUpperCase() + what.slice(1)}
      className="max-h-64 overflow-y-auto rounded-(--tool-call-result-radius) border border-line bg-paper"
    >
      {children}
    </ScrollRegion>
  );
  if (view) {
    const copy = (copied: string, of = what) => <CopyButton text={copied} what={of} />;
    const choice = (label: string, pressed: boolean, onClick: () => void) => (
      <Button variant="ghost" size="sm" aria-pressed={pressed} onClick={onClick}>
        {label}
      </Button>
    );
    return (
      <view.Formatted
        name={label}
        what={what}
        text={shown}
        cut={cut}
        shell={{ region, copy, choice }}
      />
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex min-h-7 items-center justify-between gap-2">
        <span className={TYPE.note}>{label}</span>
        <CopyButton text={shown} what={what} />
      </div>
      {/* As recorded, unescaped: the add-on's escapes would cost the first load bytes it hasn't. */}
      {region(<pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs">{shown}</pre>)}
      {cut && <p className={TYPE.note}>Cut short: the run keeps the first part of each value.</p>}
    </div>
  );
}

/** A call's detail, the third level: what it was asked and what it returned, by its tool's id. */
function CallDetail({ tool, view }: { tool: Artifactr.Tool; view: JsonView | null }) {
  const returned = STATUS[tool.status]?.[2] ?? "Result";
  return (
    <>
      <code className="font-mono text-muted text-xs">{tool.name}</code>
      <Part
        name="Arguments"
        label="What it was asked"
        tool={tool.name}
        text={tool.args}
        cut={tool.argsCut}
        view={view}
      />
      {tool.status !== "called" && (
        <Part
          name={returned}
          label={PLAIN[returned] ?? returned}
          tool={tool.name}
          text={tool.result}
          cut={tool.resultCut}
          view={view}
        />
      )}
    </>
  );
}

/** A call's status, as a badge; none for one done, which needs no word. */
function CallStatus({ tool }: { tool: Artifactr.Tool }) {
  const [tone, word] = STATUS[tool.status] ?? ["done", tool.status];
  return tool.status === "ok" ? null : (
    <StatusBadge tone={tone} className="shrink-0">
      {word}
    </StatusBadge>
  );
}

/** A call's verb and a line of what it was about: the second level, in plain words. */
function CallLine({ tool }: { tool: Artifactr.Tool }) {
  const about = callAbout(tool);
  return (
    <span className="flex min-w-0 flex-1 flex-col">
      <span>{callLabel(tool)}</span>
      {about && <bdi className="truncate text-muted text-xs">{about}</bdi>}
    </span>
  );
}

/**
 * One call, the second level: its verb and what it was about, which opens to its detail, the
 * third, whose parts each turn to their raw form, the fourth; `open` to start so.
 */
export function ToolCall({ tool, open = false }: { tool: Artifactr.Tool; open?: boolean }) {
  // The formatted view loads once the call is opened, by the reader or by a find in the page; one
  // that failed to load, as offline, is tried again as the call is opened again.
  const [opened, setOpened] = useState(open);
  const view = useRetrying(loadJsonView, opened, opened);
  return (
    <li>
      <Disclosure
        look="block"
        open={opened}
        onOpenChange={setOpened}
        className="text-sm"
        triggerClassName="min-h-10 items-center rounded-(--tool-call-radius) px-(--tool-call-pad-x) py-(--tool-call-pad-y) hover:bg-transparent"
        panelClassName="data-open:pt-0"
        summary={
          <>
            <CallLine tool={tool} />
            <CallStatus tool={tool} />
          </>
        }
      >
        <div className="flex flex-col gap-3 px-(--tool-call-pad-x) pb-3">
          <CallDetail tool={tool} view={view} />
        </div>
      </Disclosure>
    </li>
  );
}

/** A run's calls, as one list in its thread. */
export function ToolCalls({ children }: { children: ReactNode }) {
  return (
    <li>
      <ul aria-label="Tools" className="flex flex-col gap-1">
        {children}
      </ul>
    </li>
  );
}

/**
 * A group of calls on a phone: a sheet titled by what they did, listing the calls (the second
 * level), each going on to its detail (the third, whose parts turn raw, the fourth); Back returns
 * to the list, the focus following.
 */
function ToolSheet({
  open,
  onOpenChange,
  title,
  tools,
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  tools: readonly (readonly [string, Artifactr.Tool])[];
  finalFocus: RefObject<HTMLElement | null>;
}) {
  // A drag down closes as Close does, back to the list for the next time.
  const asSheet = useSheet(open, () => close(false));
  const view = useRetrying(loadJsonView, open, open);
  const [chosen, setChosen] = useState<string | null>(null);
  // The call last opened, whose row takes the focus back from its detail.
  const [left, setLeft] = useState<string | null>(null);
  const tool = tools.find(([call]) => call === chosen)?.[1];
  const back = () => {
    setLeft(chosen);
    setChosen(null);
  };
  const close = (next: boolean, details?: { reason: string; cancel: () => void }) => {
    // Escape from a call's detail goes back to the list; from the list, it closes.
    if (!next && chosen !== null && details?.reason === "escape-key") {
      details.cancel();
      back();
      return;
    }
    if (!next) {
      setChosen(null);
      setLeft(null);
    }
    onOpenChange(next);
  };
  // A sheet on a phone (portalr ADR-0082), as the kit's dialog is, with its ways out at its top:
  // a round Close over the list, a round Back over a call.
  return (
    <BaseDialog.Root open={open} onOpenChange={close}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className={backdrop} />
        <BaseDialog.Popup
          ref={asSheet}
          onKeyDown={(event) => keepTabWithin(event.currentTarget, event.nativeEvent)}
          className={`${popup} ${sheet}`}
          finalFocus={finalFocus}
        >
          <SheetHandle />
          <div className="flex items-center gap-2">
            {tool ? (
              <IconButton
                label="Back to the calls"
                icon={glyphs.chevronLeft}
                className="rounded-full bg-wash"
                // The focus moves with the reader: to Back, and from it to the call's row.
                autoFocus
                onClick={back}
              />
            ) : (
              <BaseDialog.Close
                render={
                  <IconButton label="Close" icon={glyphs.x} className="rounded-full bg-wash" />
                }
              />
            )}
            <BaseDialog.Title className={`${TYPE.section} line-clamp-2 min-w-0 flex-1`}>
              {tool ? callLabel(tool) : title}
            </BaseDialog.Title>
          </div>
          {tool ? (
            <div key={chosen} className="flex flex-col gap-3 text-sm">
              <CallDetail tool={tool} view={view} />
            </div>
          ) : (
            <ol aria-label="Tool calls" className="flex flex-col">
              {tools.map(([call, each]) => (
                <li key={call} className="border-line border-s ps-2">
                  <BaseButton
                    autoFocus={call === left}
                    onClick={() => setChosen(call)}
                    className={`flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-(--tool-call-radius) py-2 text-start text-sm ${RING}`}
                  >
                    <CallLine tool={each} />
                    <CallStatus tool={each} />
                    <Icon
                      icon={glyphs.chevronRight}
                      className="size-3.5 shrink-0 text-muted rtl:-scale-x-100"
                    />
                  </BaseButton>
                </li>
              ))}
            </ol>
          )}
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}

/** Where motion is welcome and colours are the page's own: a running group's words shimmer. */
const SHIMMERS = "(prefers-reduced-motion: no-preference) and (forced-colors: none)";

/**
 * A light passing over a running group's words, drawn here rather than in the stylesheet every
 * page loads: their colour a gradient clipped to the text, moved across them. Purely visual.
 */
function useShimmer(running: boolean) {
  const words = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const element = words.current;
    if (!running || element === null || !matchMedia(SHIMMERS).matches) {
      return;
    }
    element.style.cssText =
      "background:linear-gradient(90deg,var(--muted) 40%,var(--fg),var(--muted) 60%) 0/300%;background-clip:text;color:transparent";
    const moving = element.animate(
      { backgroundPosition: ["100%", "0%"] },
      { duration: 2e3, iterations: 1 / 0 },
    );
    return () => {
      moving.cancel();
      element.style.cssText = "";
    };
  }, [running]);
  return words;
}

/** Which groups the reader unfurled, by their first call, for the page's life: never stored. */
const opened = new Map<string, boolean>();

/**
 * A run's calls in a row as one quiet line (portalr ADR-0053): what they did, in plain words,
 * the first level, shimmering while a call runs, with how many failed, and a caret. It opens,
 * when tapped, to the calls (the second level): beneath it on a desktop, in a sheet on a phone,
 * where the list goes on to a call's detail. Closed until the reader opens it, as calls arrive.
 */
export function RunSteps({
  tools,
  running: runRunning = false,
}: {
  tools: readonly (readonly [string, Artifactr.Tool])[];
  /** Whether its run runs: between one call's answer and the next, the group still does. */
  running?: boolean;
}) {
  const key = tools[0]?.[0] ?? "";
  const phone = usePhone();
  // How it is open, chosen at the tap from what the window is then: beneath, or a sheet. Only an
  // unfurl is kept, so a sheet is never opened again by itself as the thread is shown again.
  const [shown, setShown] = useState<"list" | "sheet" | null>(() =>
    opened.get(key) ? "list" : null,
  );
  const show = (next: "list" | "sheet" | null) => {
    opened.set(key, next === "list");
    setShown(next);
  };
  const open = shown !== null;
  // The sheet is mounted once first opened, so a thread of many groups mounts none until then.
  const [sheeted, setSheeted] = useState(false);
  if (shown === "sheet" && !sheeted) {
    setSheeted(true);
  }
  const button = useRef<HTMLButtonElement>(null);
  const panel = useId();
  const calls = tools.map(([, tool]) => tool);
  const { labels, failed, running } = foldSummary(calls, runRunning);
  const full = labels[0] ?? "";
  const words = useShimmer(running);
  const marker = failed > 0 ? ` · ${failed} failed` : "";
  const count = `${tools.length} tool call${tools.length === 1 ? "" : "s"}`;
  // The line says the longest of its ways that fits, measured, where it is set, again as the
  // line's own box, whose width its words don't change, as the button's they do, changes, and again
  // as a face loads, which may make the words wider or narrower. The button's name starts with
  // what the line says, so the name a voice user speaks is the one they see, and goes on to all of
  // it (as the sheet's title does).
  const ways = labels.join("\n");
  useLayoutEffect(() => {
    const box = words.current;
    const line = button.current?.parentElement;
    if (!(box && line)) {
      return;
    }
    const fit = () => {
      const all = ways.split("\n");
      for (const said of all) {
        box.textContent = said;
        if (box.scrollWidth <= box.clientWidth) {
          break;
        }
      }
      const said = box.textContent;
      button.current?.setAttribute(
        "aria-label",
        said === all[0] ? `${said}${marker}: ${count}` : `${said}${marker}: ${all[0]}, ${count}`,
      );
    };
    fit();
    const resized = new ResizeObserver(fit);
    resized.observe(line);
    document.fonts.addEventListener("loadingdone", fit);
    return () => {
      resized.disconnect();
      document.fonts.removeEventListener("loadingdone", fit);
    };
  }, [ways, marker, count]);
  // Said once, as a group that was running ends: never as each call does.
  const [ran, setRan] = useState(running);
  // What is said as the run ends, kept as it was then: a later change to the line says nothing.
  const [said, setSaid] = useState("");
  if (ran !== running) {
    setRan(running);
    setSaid(running ? "" : `${full}${marker}`);
  }
  return (
    // On a phone its target, 44px, overlaps what is above and below it, as its words are not that tall.
    <li className="flex flex-col phone:-my-1.5">
      <BaseButton
        ref={button}
        aria-expanded={open}
        // What it opens as it is open, or, closed, what a tap here would open.
        {...((shown ?? (phone ? "sheet" : "list")) === "sheet"
          ? { "aria-haspopup": "dialog" as const }
          : { "aria-controls": panel })}
        onClick={() => show(open ? null : phoneNow() ? "sheet" : "list")}
        className={cn(
          "flex min-h-(--disclosure-target) max-w-full cursor-pointer items-center gap-1.5 self-start rounded-(--disclosure-radius) text-muted text-xs hover:text-fg phone:min-h-11",
          RING,
        )}
      >
        <Icon icon={glyphs.wrench} className="size-3.5 shrink-0" />
        <span ref={words} className="min-w-0 truncate" />
        {failed > 0 && (
          <span className="flex shrink-0 items-center gap-1 text-danger">
            <Icon icon={glyphs.circleAlert} className="size-3.5" />
            {failed} failed
          </span>
        )}
        <Icon
          icon={glyphs.chevronRight}
          className={`size-3.5 shrink-0 transition-transform duration-(--disclosure-duration) motion-reduce:transition-none rtl:-scale-x-100 ${shown === "list" ? "rotate-90" : ""}`}
        />
      </BaseButton>
      <span role="status" className="sr-only">
        {said}
      </span>
      {shown === "list" && (
        <ol
          id={panel}
          aria-label="Tool calls"
          className="ms-1.5 flex flex-col border-line border-s ps-2"
        >
          {tools.map(([call, tool]) => (
            <ToolCall key={call} tool={tool} />
          ))}
        </ol>
      )}
      {sheeted && (
        <ToolSheet
          open={shown === "sheet"}
          onOpenChange={(next) => show(next ? "sheet" : null)}
          title={`${full}${marker}`}
          tools={tools}
          finalFocus={button}
        />
      )}
    </li>
  );
}
