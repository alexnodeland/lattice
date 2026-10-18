/**
 * Charts on Recharts, adapted from Tremor's BarChart, LineChart and DonutChart (Apache-2.0; see
 * NOTICE): only what admin draws, restyled to the kit's tokens. Everything the three share, a
 * palette and the patterns that tell a series apart beyond its hue, margins, axes, the tooltip and
 * the legend, and how numbers and dates are written, is `chart-theme.tsx`, so no chart writes a
 * colour, a dash or a pattern of its own (portalr ADR-0036). Each series is named in a legend,
 * and, where there are several, directly at its last mark; the figures are a table beneath, for
 * those who read them rather than look. Text takes the kit's type: the chart's small size,
 * inherited, in the muted ink.
 */

import { type ReactNode, useId, useRef } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  Line,
  Pie,
  PieChart,
  BarChart as RechartsBarChart,
  LineChart as RechartsLineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  usePlotArea,
  useYAxisScale,
  XAxis,
  YAxis,
} from "recharts";
import {
  ADJACENT,
  AXIS,
  dash,
  fill,
  formatNumber,
  GRID,
  Hatch,
  ink,
  LABELS_OFFSET,
  type Labels,
  Legend,
  largestFirst,
  MARGIN,
  MAX_SERIES,
  type Margin,
  Marker,
  Swatch,
  TooltipCard,
  TooltipRow,
  useLabels,
} from "./chart-theme";
import { type Column, ItemTable } from "./item-table";
import { Num } from "./num";

export { MAX_SERIES } from "./chart-theme";

/** A row of a chart: its index, such as a day, and each series' value on it, or none. */
export type Datum = Readonly<Record<string, string | number | null>>;

/** One series of a chart: the key its values are under in each row, and its name. */
export interface Series {
  readonly key: string;
  readonly name: string;
}

/** What a chart's rows are indexed by: the key, and its name, such as "Day (UTC)". */
interface Index {
  readonly key: string;
  readonly name: string;
}

/** The least number that is at least `most`, is one of 1, 2, 4, 6, 8 or 10 tens, and at least 2: it halves into whole numbers. */
const evenReach = (most: number) => {
  const tens = 10 ** Math.floor(Math.log10(Math.max(most, 1)));
  return Math.max(2, tens * ([1, 2, 4, 6, 8, 10].find((step) => step * tens >= most) ?? 10));
};

/** The room a diverging chart keeps to its left for the names of its two halves, in px. */
const CAPTION_ROOM = 20;

/** A chart's frame: what it shows, as a figure's caption, its legend, and its figures as a table. */
function Figure({
  label,
  index,
  series,
  data,
  shown,
  line = false,
  adjacent = false,
  labelled = false,
  left = MARGIN.left,
  bare = false,
  children,
}: {
  label: string;
  index: Index;
  series: readonly Series[];
  data: readonly Datum[];
  /** A value as the table shows it. */
  shown: (value: number) => string;
  line?: boolean;
  /** Whether a series' mark touches another's, which a pattern tells apart. */
  adjacent?: boolean;
  /** Whether each series is named at its last mark, in a margin to the plot's right. */
  labelled?: boolean;
  /** The room to keep to the plot's left, for what is written there. */
  left?: number;
  /** Its legend and drawing alone: the caller frames it, with a caption and the figures. */
  bare?: boolean;
  /** The drawing, given the margin to draw it in. */
  children: (margin: Margin, labels: Labels) => ReactNode;
}) {
  const caption = useId();
  const plot = useRef<HTMLDivElement>(null);
  const labels = useLabels(plot, labelled ? series.map((one) => one.name) : []);
  const columns: [Column<Datum>, ...Column<Datum>[]] = [
    { key: "~index", label: index.name, cell: (row) => row[index.key] },
    ...series.map((one) => ({
      key: one.key,
      label: one.name,
      cell: (row: Datum) => {
        const value = row[one.key];
        return typeof value === "number" ? shown(value) : "–";
      },
    })),
  ];
  const drawn = (
    <>
      <Legend
        entries={series.map((one, at) => ({
          key: one.key,
          name: one.name,
          mark: <Swatch at={at} line={line} />,
        }))}
      />
      <div ref={plot} className="h-64 w-full text-muted text-xs" aria-hidden="true">
        {children({ ...MARGIN, left, right: labelled ? labels.room : MARGIN.right }, labels)}
      </div>
    </>
  );
  if (bare) {
    return (
      <div className="flex flex-col gap-2" {...(adjacent && { style: ADJACENT })}>
        {drawn}
      </div>
    );
  }
  return (
    <figure
      aria-labelledby={caption}
      className="flex flex-col gap-2"
      {...(adjacent && { style: ADJACENT })}
    >
      <figcaption id={caption} className="font-semibold text-fg text-sm">
        {label}
      </figcaption>
      {drawn}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted">Show the figures</summary>
        <ItemTable
          caption={label}
          columns={columns}
          items={data}
          keyOf={(row) => String(row[index.key])}
          empty={{ title: "No figures", body: "Nothing in this chart yet." }}
        />
      </details>
    </figure>
  );
}

/** A tooltip over a chart: the index, then each series' mark, name and value. */
function ChartTooltip({
  active,
  payload,
  label,
  series,
  shown,
  line = false,
}: Pick<TooltipContentProps<number, string>, "active" | "payload" | "label"> & {
  series: readonly Series[];
  shown: (value: number) => string;
  line?: boolean;
}) {
  if (!active || payload.length === 0) {
    return null;
  }
  return (
    <TooltipCard title={label}>
      {payload.map((item) => {
        const at = series.findIndex((one) => one.key === item.dataKey);
        return (
          <TooltipRow
            key={String(item.dataKey)}
            mark={<Swatch at={at} line={line} />}
            name={series[at]?.name ?? String(item.name)}
            value={typeof item.value === "number" ? shown(item.value) : "–"}
          />
        );
      })}
    </TooltipCard>
  );
}

/** The axes and grid both charts share. */
function Axes({
  index,
  shown,
  domain,
  ticks,
  tick,
  whole,
}: {
  index: string;
  shown: (value: number) => string;
  domain?: readonly [number, number] | undefined;
  /** Where the value axis is marked, where it is not Recharts' own choice. */
  ticks?: readonly number[] | undefined;
  /** An index as the axis writes it, where it is shorter than the table's and the tooltip's. */
  tick?: ((index: string) => string) | undefined;
  /** Whether the value axis is of whole numbers, such as counts, and so has no tick between them. */
  whole: boolean;
}) {
  return (
    <>
      <CartesianGrid {...GRID} />
      <XAxis dataKey={index} minTickGap={16} {...AXIS} {...(tick && { tickFormatter: tick })} />
      <YAxis
        width="auto"
        allowDecimals={!whole}
        {...AXIS}
        {...(domain && { domain: [...domain] })}
        {...(ticks && { ticks: [...ticks] })}
        tickFormatter={shown}
      />
    </>
  );
}

/**
 * The first rows of a chart that are unknown, rather than empty, shaded and named so: a read that
 * stopped short of them. Their values are none, so the table shows them as "–".
 */
function Unknown({ data, index, rows }: { data: readonly Datum[]; index: string; rows: number }) {
  const first = data[0]?.[index];
  const last = data[Math.min(rows, data.length) - 1]?.[index];
  if (rows <= 0 || first === undefined || last === undefined || first === null || last === null) {
    return null;
  }
  return (
    <ReferenceArea
      x1={first}
      x2={last}
      fill="var(--line)"
      fillOpacity={0.6}
      stroke="none"
      ifOverflow="extendDomain"
      label={{ value: "Not read", position: "insideTop", fill: "var(--muted)" }}
    />
  );
}

/** Where a series is last drawn: its value in the last row it has one in, other than none. */
function lastValue(data: readonly Datum[], key: string, bar: boolean): number | null {
  const row = data.findLast((one) => {
    const value = one[key];
    return typeof value === "number" && !(bar && value === 0);
  });
  const value = row?.[key];
  return typeof value === "number" ? value : null;
}

/** How far apart direct labels are kept, in px: a line of the chart's text. */
const LABELS_APART = 12;

/**
 * Each series' name, in the margin to the plot's right, beside where it is last drawn: a line's
 * last point, or the middle of a bar series' last bar. The places are worked out from the data
 * and the chart's scale, kept inside the plot's height, then nudged apart, `LABELS_APART` at least,
 * before anything is drawn; a name too long for the margin is cut, and given whole as a title.
 */
function DirectLabels({
  data,
  series,
  fit,
  bar = false,
}: {
  data: readonly Datum[];
  series: readonly Series[];
  /** A name as it is written: whole, or cut. */
  fit: (name: string) => string;
  bar?: boolean;
}) {
  const scale = useYAxisScale();
  const plot = usePlotArea();
  if (!scale || !plot) {
    return null;
  }
  const top = plot.y + LABELS_APART / 2;
  const bottom = plot.y + plot.height - LABELS_APART / 2;
  const placed = series
    .flatMap((one) => {
      const value = lastValue(data, one.key, bar);
      const y = value === null ? undefined : scale(bar ? value / 2 : value);
      return typeof y === "number"
        ? [{ name: one.name, written: fit(one.name), y: Math.min(Math.max(y, top), bottom) }]
        : [];
    })
    .sort((a, b) => a.y - b.y);
  // Each a gap below the one above, at least, so none overlaps; then, from the bottom, each a gap
  // above the one below, so none is pushed out of the plot.
  for (const [at, label] of placed.entries()) {
    const above = placed[at - 1];
    if (above) {
      placed[at] = { ...label, y: Math.max(label.y, above.y + LABELS_APART) };
    }
  }
  for (let at = placed.length - 1; at >= 0; at -= 1) {
    const label = placed[at];
    const below = placed[at + 1];
    if (label) {
      placed[at] = { ...label, y: Math.min(label.y, below ? below.y - LABELS_APART : bottom) };
    }
  }
  return (
    <g>
      {placed.map((label) => (
        <text
          key={label.name}
          x={plot.x + plot.width + LABELS_OFFSET}
          y={label.y + 4}
          fill="var(--muted)"
          textAnchor="start"
        >
          {label.written !== label.name && <title>{label.name}</title>}
          {label.written}
        </text>
      ))}
    </g>
  );
}

/**
 * The names of a diverging chart's two halves, at the plot's left, turned to read along the axis:
 * the first series above the baseline, and the second below it, whose ticks count up from it.
 */
function Halves({ above, below }: { above: string; below: string }) {
  const scale = useYAxisScale();
  const plot = usePlotArea();
  const zero = scale?.(0);
  if (!plot || typeof zero !== "number") {
    return null;
  }
  const half = (name: string, middle: number) => (
    <text
      key={name}
      transform={`translate(${CAPTION_ROOM / 2} ${middle}) rotate(-90)`}
      fill="var(--muted)"
      textAnchor="middle"
      dominantBaseline="middle"
    >
      {name}
    </text>
  );
  return (
    <g>
      {half(above, (plot.y + zero) / 2)}
      {half(below, (zero + plot.y + plot.height) / 2)}
    </g>
  );
}

/**
 * Bars per index, one series beside another, or, with `diverging`, the first series above the
 * baseline and the second below it, such as thumbs up and down, their values counts drawn apart:
 * the axis, the tooltip and the table show each as the count it is, and the halves are named at
 * the axis. Where the series meet at a baseline, the second is hatched, as marks that touch are.
 */
export function BarChart({
  label,
  data,
  index,
  series,
  format = formatNumber,
  diverging = false,
  whole = false,
  unknown = 0,
  tick,
  bare = false,
}: {
  label: string;
  data: readonly Datum[];
  index: Index;
  series: readonly Series[];
  format?: (value: number) => string;
  diverging?: boolean;
  /** Whether the values are whole numbers, such as counts, which an axis then marks only at. */
  whole?: boolean;
  /** How many of the first rows are unknown, rather than empty: shaded, and named so. */
  unknown?: number;
  /** An index as the axis writes it, such as a date without its year; the rows keep it whole. */
  tick?: (index: string) => string;
  /** Its legend and drawing alone: the caller frames it, with a caption and the figures. */
  bare?: boolean;
}) {
  const id = useId();
  const drawn = series.slice(0, MAX_SERIES);
  const below = diverging ? drawn[1] : undefined;
  const rows = below
    ? data.map((row) => {
        const value = row[below.key];
        return typeof value === "number" ? { ...row, [below.key]: -value } : row;
      })
    : data;
  // Below the baseline is a count all the same: shown without its sign.
  const shown = diverging ? (value: number) => format(Math.abs(value)) : format;
  // Both halves reach as far, to a number that halves evenly, so the baseline is the middle and a
  // tick's distance from it is a count.
  const reach = diverging
    ? evenReach(
        Math.max(
          0,
          ...rows.flatMap((row) => drawn.map((one) => Math.abs(Number(row[one.key] ?? 0)))),
        ),
      )
    : 0;
  return (
    <Figure
      label={label}
      index={index}
      series={drawn}
      data={data}
      shown={format}
      adjacent={diverging}
      bare={bare}
      labelled={drawn.length > 1 && !diverging}
      left={diverging ? CAPTION_ROOM : MARGIN.left}
    >
      {(margin, labels) => (
        <ResponsiveContainer>
          <RechartsBarChart
            data={[...rows]}
            stackOffset={diverging ? "sign" : "none"}
            barCategoryGap="20%"
            margin={margin}
          >
            <defs>
              {drawn.map((one, at) => at > 0 && <Hatch key={one.key} id={`${id}-${at}`} at={at} />)}
            </defs>
            <Axes
              index={index.key}
              shown={shown}
              tick={tick}
              whole={whole}
              {...(diverging && {
                domain: [-reach, reach] as const,
                ticks: [-reach, -reach / 2, 0, reach / 2, reach],
              })}
            />
            <Unknown data={rows} index={index.key} rows={unknown} />
            {diverging && <ReferenceLine y={0} stroke="var(--edge)" />}
            <Tooltip
              cursor={{ fill: "var(--wash)" }}
              content={(props) => <ChartTooltip {...props} series={drawn} shown={shown} />}
            />
            {drawn.map((one, at) => (
              <Bar
                key={one.key}
                dataKey={one.key}
                name={one.name}
                fill={fill(id, at)}
                radius={4}
                isAnimationActive={false}
                {...(diverging && { stackId: "sign" })}
              />
            ))}
            {diverging && below && drawn[0] && <Halves above={drawn[0].name} below={below.name} />}
            {drawn.length > 1 && !diverging && (
              <DirectLabels data={rows} series={drawn} fit={labels.fit} bar />
            )}
          </RechartsBarChart>
        </ResponsiveContainer>
      )}
    </Figure>
  );
}

/** A line per series over the index, such as a mean per day, with a gap where a day has none. */
export function LineChart({
  label,
  data,
  index,
  series,
  format = formatNumber,
  domain,
  unknown = 0,
  tick,
  bare = false,
}: {
  label: string;
  data: readonly Datum[];
  index: Index;
  series: readonly Series[];
  format?: (value: number) => string;
  /** The value axis's ends, such as [0, 1] for a rate; Recharts' own where none is given. */
  domain?: readonly [number, number];
  /** How many of the first rows are unknown, rather than empty: shaded, and named so. */
  unknown?: number;
  /** An index as the axis writes it, such as a date without its year; the rows keep it whole. */
  tick?: (index: string) => string;
  /** Its legend and drawing alone: the caller frames it, with a caption and the figures. */
  bare?: boolean;
}) {
  const drawn = series.slice(0, MAX_SERIES);
  return (
    <Figure
      label={label}
      index={index}
      series={drawn}
      data={data}
      shown={format}
      bare={bare}
      line
      labelled={drawn.length > 1}
    >
      {(margin, labels) => (
        <ResponsiveContainer>
          <RechartsLineChart data={[...data]} margin={margin}>
            <Axes index={index.key} shown={format} domain={domain} tick={tick} whole={false} />
            <Unknown data={data} index={index.key} rows={unknown} />
            <Tooltip
              cursor={{ stroke: "var(--edge)" }}
              content={(props) => <ChartTooltip {...props} series={drawn} shown={format} line />}
            />
            {drawn.map((one, at) => (
              <Line
                key={one.key}
                dataKey={one.key}
                name={one.name}
                stroke={ink(at)}
                strokeWidth={2}
                style={{ strokeDasharray: dash(at) }}
                dot={({ cx, cy, index: point }) =>
                  typeof cx === "number" && typeof cy === "number" ? (
                    <Marker key={point} at={at} x={cx} y={cy} />
                  ) : (
                    <g key={point} />
                  )
                }
                activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
            {drawn.length > 1 && <DirectLabels data={data} series={drawn} fit={labels.fit} />}
          </RechartsLineChart>
        </ResponsiveContainer>
      )}
    </Figure>
  );
}

/** One part of a whole: its key, its name, and how much of it. */
export interface Part {
  readonly key: string;
  readonly name: string;
  readonly value: number;
}

/** The key "Other" is kept under: no part's key starts with "~". */
const OTHER = "~other";

/**
 * A whole in parts, as a donut with its total at its centre, beside a list of its parts, each
 * with its value and share in its own row: the largest three in the inks, and the rest folded
 * into "Other", dotted in the muted ink. Its slices are set apart by gaps, so they stay solid. The
 * list names every part in the donut; the figures are a table beneath, as every chart's are.
 */
export function DonutChart({
  label,
  parts,
  format = formatNumber,
  bare = false,
}: {
  label: string;
  parts: readonly Part[];
  format?: (value: number) => string;
  /** Its legend and drawing alone: the caller frames it, with a caption and the figures. */
  bare?: boolean;
}) {
  const id = useId();
  const caption = useId();
  const { sorted, total, share } = largestFirst(parts);
  const rest = sorted.slice(MAX_SERIES).reduce((sum, part) => sum + part.value, 0);
  // Folded into "Other", the parts keep their total, so each share is the same.
  const shown: Part[] = [
    ...sorted.slice(0, MAX_SERIES),
    ...(rest > 0 ? [{ key: OTHER, name: "Other", value: rest }] : []),
  ];
  const drawn = (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
      <div className="relative size-40 shrink-0">
        <div className="size-full" aria-hidden="true">
          <ResponsiveContainer>
            <PieChart>
              <defs>
                {shown.map(
                  (part, at) => at > 0 && <Hatch key={part.key} id={`${id}-${at}`} at={at} />,
                )}
              </defs>
              <Pie
                data={[...shown]}
                dataKey="value"
                nameKey="name"
                innerRadius="70%"
                outerRadius="100%"
                startAngle={90}
                endAngle={-270}
                stroke="var(--surface)"
                strokeWidth={2}
                isAnimationActive={false}
              >
                {shown.map((part, at) => (
                  <Cell key={part.key} fill={fill(id, at)} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  const part = payload[0];
                  const at = shown.findIndex((one) => one.key === part?.payload?.key);
                  return active && part && typeof part.value === "number" ? (
                    <TooltipCard>
                      <TooltipRow
                        mark={<Swatch at={at} />}
                        name={String(part.name)}
                        value={`${format(part.value)} · ${share(part.value)}`}
                      />
                    </TooltipCard>
                  ) : null;
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <p className="pointer-events-none absolute inset-0 m-auto flex size-24 flex-col items-center justify-center text-center">
          <span className="text-muted text-xs">Total</span>
          <span className="font-semibold text-fg text-lg">
            <Num>{format(total)}</Num>
          </span>
        </p>
      </div>
      <ul className="grid w-fit grid-cols-[auto_auto_auto] gap-x-5 gap-y-1.5 text-sm">
        {shown.map((part, at) => (
          <li key={part.key} className="col-span-3 grid grid-cols-subgrid items-center">
            <span className="inline-flex items-center gap-2 text-fg">
              <Swatch at={at} />
              {part.name}
            </span>
            <span className="sr-only">, </span>
            <span className="text-right text-fg">
              <Num>{format(part.value)}</Num>
            </span>
            <span className="sr-only">, </span>
            <span className="text-right text-muted">
              <Num>{share(part.value)}</Num>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
  if (bare) {
    return drawn;
  }
  return (
    <figure aria-labelledby={caption} className="flex flex-col gap-2">
      <figcaption id={caption} className="font-semibold text-fg text-sm">
        {label}
      </figcaption>
      {drawn}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted">Show the figures</summary>
        <ItemTable
          caption={label}
          columns={[
            { key: "part", label: "Part", cell: (part) => part.name },
            { key: "value", label: "Value", cell: (part) => format(part.value) },
            { key: "share", label: "Share", cell: (part) => share(part.value) },
          ]}
          items={sorted}
          keyOf={(part) => part.key}
          empty={{ title: "No parts", body: "Nothing in this whole yet." }}
        />
      </details>
    </figure>
  );
}
