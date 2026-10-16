/**
 * What every chart shares, in one place (portalr ADR-0036): its palette and the patterns that tell
 * a series apart beyond its hue, margins, axes and gridlines, the tooltip and the legend, and how
 * numbers and dates are written. The inks and patterns are not here but in `tokens.css`, as custom
 * properties a chart only reads, so a mode that changes them (`data-cvd`) needs no chart to
 * change: no colour, dash or pattern is written in a chart's own code.
 */

import {
  type CSSProperties,
  type ReactNode,
  type RefObject,
  useId,
  useLayoutEffect,
  useState,
} from "react";
import { popover } from "./menu";
import { Num } from "./num";

/** The most series a chart draws, one per ink. */
export const MAX_SERIES = 3;

/** A series' number for the tokens that name it, from 1: past the inks, the last. */
const slot = (at: number) => Math.min(at, MAX_SERIES - 1) + 1;

/** A series' ink, by its place among the series; past the inks, what is folded into "Other". */
export const ink = (at: number) => (at < MAX_SERIES ? `var(--chart-${at + 1})` : "var(--muted)");

/** A series' line dash, by its place: unbroken unless the mode dashes it. */
export const dash = (at: number) => `var(--chart-dash-${slot(at)})`;

/** A mark that touches another, which a pattern tells apart: the hatch its fill takes, at full. */
export const ADJACENT = { "--chart-hatch": "var(--chart-hatched)" } as CSSProperties;

/** The room a chart keeps round its drawing, in px. */
export interface Margin {
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly left: number;
}

/** A chart's margin by default; its right grows for direct labels, when it has any. */
export const MARGIN: Margin = { top: 12, right: 8, bottom: 0, left: 4 };

/** The gridlines: very light, and horizontal only. */
export const GRID = { stroke: "var(--chart-grid)", vertical: false } as const;

/** An axis: recessive, in the muted ink, with no line and no ticks. */
export const AXIS = {
  tickLine: false,
  axisLine: false,
  tickMargin: 8,
  tick: { fill: "var(--muted)" },
} as const;

/** The stripes of a fill past a series' first: the ink, hatched over by the surface where the mode asks. */
export function Hatch({ id, at }: { id: string; at: number }) {
  if (at >= MAX_SERIES) {
    return (
      <pattern id={id} width="4" height="4" patternUnits="userSpaceOnUse">
        <rect width="4" height="4" fill="var(--muted)" opacity={0.3} />
        <circle cx="2" cy="2" r="1" fill="var(--muted)" />
      </pattern>
    );
  }
  return (
    <pattern
      id={id}
      width="6"
      height="6"
      patternUnits="userSpaceOnUse"
      patternTransform={`rotate(${at === 1 ? 45 : 135})`}
    >
      <rect width="6" height="6" fill={ink(at)} />
      <line
        x1="0"
        y1="0"
        x2="0"
        y2="6"
        stroke="var(--surface)"
        strokeWidth="2.5"
        style={{ strokeOpacity: "var(--chart-hatch)" }}
      />
    </pattern>
  );
}

/** A series' fill: its ink where it is first, else its pattern, under `id`, which `Hatch` defines. */
export const fill = (id: string, at: number) => (at === 0 ? ink(0) : `url(#${id}-${at})`);

/** A marker on a line, at a point: a shape of the mode's choosing, in the series' ink. */
export function Marker({ at, x, y }: { at: number; x: number; y: number }) {
  const place = slot(at);
  const size = "var(--chart-marker-size)";
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect
        fill={ink(at)}
        stroke="var(--surface)"
        strokeWidth={1}
        style={{
          x: `calc(${size} / -2)`,
          y: `calc(${size} / -2)`,
          width: size,
          height: size,
          rx: `calc(${size} * var(--chart-marker-corner-${place}))`,
          transform: `rotate(var(--chart-marker-turn-${place}, 0deg))`,
        }}
      />
    </g>
  );
}

/** A series' mark, small, as a legend or a tooltip shows it: a bar's fill, or a line's dash and marker. */
export function Swatch({ at, line = false }: { at: number; line?: boolean }) {
  const id = useId();
  return (
    <svg aria-hidden="true" width="16" height="10" className="shrink-0">
      {line ? (
        <>
          <line
            x1="0"
            y1="5"
            x2="16"
            y2="5"
            stroke={ink(at)}
            strokeWidth="2"
            style={{ strokeDasharray: dash(at) }}
          />
          <Marker at={at} x={8} y={5} />
        </>
      ) : (
        <>
          <defs>{at > 0 && <Hatch id={`${id}-${at}`} at={at} />}</defs>
          <rect width="16" height="10" rx="2" fill={fill(id, at)} />
        </>
      )}
    </svg>
  );
}

/** One of a legend's entries: its key, its name, and its mark. */
export interface Entry {
  readonly key: string;
  readonly name: string;
  readonly mark: ReactNode;
}

/** A chart's legend: each series' mark beside its name, in a row that wraps. */
export function Legend({ entries }: { entries: readonly Entry[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-muted text-xs">
      {entries.map((entry) => (
        <li key={entry.key} className="inline-flex items-center gap-1.5">
          {entry.mark}
          {entry.name}
        </li>
      ))}
    </ul>
  );
}

/** A tooltip, on the surface menus float on: what it is of, and a row for each series. */
export function TooltipCard({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return (
    <div className={popover}>
      {title && <p className="border-line border-b px-3 py-1.5 font-medium">{title}</p>}
      <ul className="flex flex-col gap-1 px-3 py-1.5">{children}</ul>
    </div>
  );
}

/** One of a tooltip's rows: a series' mark and name, and its value, its digits aligned. */
export function TooltipRow({
  mark,
  name,
  value,
}: {
  mark: ReactNode;
  name: string;
  value: string;
}) {
  return (
    <li className="flex items-center justify-between gap-6">
      <span className="inline-flex items-center gap-1.5 text-muted">
        {mark}
        {name}
      </span>
      <span className="font-medium">
        <Num>{value}</Num>
      </span>
    </li>
  );
}

const NUMBER = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/** A number as people read it: grouped, to two places at most, such as `1,250.5`. */
export const formatNumber = (value: number) => NUMBER.format(value);

/** A day, `2026-10-15`, as an axis writes it: `Oct 15`. */
export const formatDay = (day: string) => DAY.format(new Date(`${day}T00:00:00Z`));

/** A moment in UTC, `2026-10-15 04:11`, as an axis writes it: `04:11`, with its day too, `Oct 15 04:11`, when asked. */
export const formatMoment = (moment: string, withDay: boolean) =>
  withDay ? `${formatDay(moment.slice(0, 10))} ${moment.slice(11)}` : moment.slice(11);

/** The most of a chart's width its direct labels may take: a longer name is cut, and given whole as a title. */
const MOST_OF_WIDTH = 0.3;

/** The gap between a plot and its direct labels, in px. */
const LABEL_GAP = 8;

/** A chart's direct labels: the room they take to its right, and each name as it is written there. */
export interface Labels {
  readonly room: number;
  /** A name as its direct label: whole, or cut with an ellipsis to the most the chart allows. */
  readonly fit: (name: string) => string;
}

/**
 * The direct labels of a chart holding `ref`: each of `names` written whole where it fits within
 * `MOST_OF_WIDTH` of the chart's width, else cut to fit, measured with a canvas at the chart's own
 * font, once its faces have loaded and again as the chart is resized; and the room the widest
 * takes, and a gap. Until the first measure, it is a guess of 7px a character.
 */
export function useLabels(ref: RefObject<HTMLElement | null>, names: readonly string[]): Labels {
  const key = names.join("\n");
  const [labels, setLabels] = useState<Labels>(() => ({
    room: LABEL_GAP + 7 * Math.max(0, ...names.map((name) => name.length)),
    fit: (name) => name,
  }));
  useLayoutEffect(() => {
    const element = ref.current;
    const context = document.createElement("canvas").getContext("2d");
    if (!element || !context || key === "") {
      return;
    }
    const measure = () => {
      context.font = getComputedStyle(element).font;
      const width = (text: string) => context.measureText(text).width;
      const most = element.clientWidth * MOST_OF_WIDTH;
      const fit = (name: string) => {
        let kept = name;
        while (kept.length > 1 && width(kept === name ? kept : `${kept}…`) > most) {
          kept = kept.slice(0, -1);
        }
        return kept === name ? name : `${kept}…`;
      };
      const widest = Math.max(...key.split("\n").map((name) => width(fit(name))));
      setLabels({ room: LABEL_GAP + Math.ceil(widest), fit });
    };
    measure();
    void document.fonts.ready.then(measure);
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, key]);
  return labels;
}
