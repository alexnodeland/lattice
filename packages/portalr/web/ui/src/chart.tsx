/**
 * Charts on Recharts, adapted from Tremor's BarChart, LineChart and DonutChart (Apache-2.0; see
 * NOTICE): only what admin draws, restyled to the kit's tokens. A chart's series take the inks in
 * order, as marks and never as text, three at most, and each has a pattern too, so colour is
 * never its only cue (portalr ADR-0021): solid, then hatched one way, then the other; or a line
 * solid, dashed, then dotted. Each series is named in a legend, and directly at its last mark, and
 * the figures are a table beneath, for those who read them rather than look. Text takes the
 * kit's type: the chart's small size, inherited, in the muted ink.
 */

import { type ReactNode, useId } from "react";
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
import { type Column, ItemTable } from "./item-table";

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

/** The most series a chart draws, one per ink. */
export const MAX_SERIES = 3;

const INKS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)"] as const;
const DASHES = ["0", "6 3", "2 3"] as const;

/** A series' ink and dash, by its place among the series. */
const ink = (at: number) => INKS[at] ?? "var(--muted)";
const dash = (at: number) => DASHES[at] ?? "0";

/** The longest a direct label is, in characters: a longer name is cut, and given whole as a title. */
const LONGEST_LABEL = 14;

/** A series' name as its direct label: cut to `LONGEST_LABEL`, with an ellipsis. */
const cut = (name: string) =>
  name.length > LONGEST_LABEL ? `${name.slice(0, LONGEST_LABEL - 1)}…` : name;

/** The room a chart keeps to its right for its direct labels: enough for the longest, cut. */
const labelRoom = (series: readonly Series[]) =>
  16 + 6 * Math.max(0, ...series.map((one) => cut(one.name).length));

/**
 * A series' pattern past the first, which is solid: its ink hatched at 45°, then at 135°; past
 * the inks, for what is folded into "Other", the muted ink, dotted.
 */
function Hatch({ id, at }: { id: string; at: number }) {
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
      <rect width="6" height="6" fill={ink(at)} opacity={0.35} />
      <line x1="0" y1="0" x2="0" y2="6" stroke={ink(at)} strokeWidth="3" />
    </pattern>
  );
}

/** A series' mark, small, as a legend or a tooltip shows it: its own pattern, under its own id. */
function Swatch({ at, line = false }: { at: number; line?: boolean }) {
  const id = useId();
  return (
    <svg aria-hidden="true" width="16" height="10" className="shrink-0">
      {line ? (
        <line
          x1="0"
          y1="5"
          x2="16"
          y2="5"
          stroke={ink(at)}
          strokeWidth="2"
          strokeDasharray={dash(at)}
        />
      ) : (
        <>
          <defs>{at > 0 && <Hatch id={id} at={at} />}</defs>
          <rect width="16" height="10" rx="2" fill={at === 0 ? ink(0) : `url(#${id})`} />
        </>
      )}
    </svg>
  );
}

/** A chart's frame: what it shows, as a figure's caption, its legend, and its figures as a table. */
function Figure({
  label,
  index,
  series,
  data,
  shown,
  line = false,
  children,
}: {
  label: string;
  index: Index;
  series: readonly Series[];
  data: readonly Datum[];
  /** A value as the table shows it. */
  shown: (value: number) => string;
  line?: boolean;
  children: ReactNode;
}) {
  const caption = useId();
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
  return (
    <figure aria-labelledby={caption} className="flex flex-col gap-2">
      <figcaption id={caption} className="font-semibold text-fg text-sm">
        {label}
      </figcaption>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-muted text-xs">
        {series.map((one, at) => (
          <li key={one.key} className="inline-flex items-center gap-1.5">
            <Swatch at={at} line={line} />
            {one.name}
          </li>
        ))}
      </ul>
      <div className="h-64 w-full text-muted text-xs" aria-hidden="true">
        {children}
      </div>
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

/** Tremor's tooltip: the index, then each series' mark, name and value, in the kit's colours. */
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
    <div className="rounded-md border border-line bg-surface text-sm shadow-md">
      <p className="border-line border-b px-3 py-1.5 font-medium text-fg">{label}</p>
      <ul className="flex flex-col gap-1 px-3 py-1.5">
        {payload.map((item) => {
          const at = series.findIndex((one) => one.key === item.dataKey);
          return (
            <li key={String(item.dataKey)} className="flex items-center justify-between gap-6">
              <span className="inline-flex items-center gap-1.5 text-muted">
                <Swatch at={at} line={line} />
                {series[at]?.name ?? item.name}
              </span>
              <span className="font-medium text-fg tabular-nums">
                {typeof item.value === "number" ? shown(item.value) : "–"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** The axes and grid both charts share: recessive, in the muted ink, with no ticks. */
function Axes({
  index,
  shown,
  domain,
  tick,
}: {
  index: string;
  shown: (value: number) => string;
  domain?: readonly [number, number] | undefined;
  /** An index as the axis writes it, where it is shorter than the table's and the tooltip's. */
  tick?: ((index: string) => string) | undefined;
}) {
  return (
    <>
      <CartesianGrid stroke="var(--line)" vertical={false} />
      <XAxis
        dataKey={index}
        tickLine={false}
        axisLine={false}
        stroke="var(--muted)"
        minTickGap={16}
        {...(tick && { tickFormatter: tick })}
      />
      <YAxis
        tickLine={false}
        axisLine={false}
        stroke="var(--muted)"
        width={40}
        {...(domain && { domain: [...domain] })}
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
const LABEL_GAP = 12;

/**
 * Each series' name, in the margin to the plot's right, beside where it is last drawn: a line's
 * last point, or the middle of a bar series' last bar. The places are worked out from the data
 * and the chart's scale, kept inside the plot's height, then nudged apart, `LABEL_GAP` at least,
 * before anything is drawn; a name too long for the margin is cut, and given whole as a title.
 */
function DirectLabels({
  data,
  series,
  bar = false,
}: {
  data: readonly Datum[];
  series: readonly Series[];
  bar?: boolean;
}) {
  const scale = useYAxisScale();
  const plot = usePlotArea();
  if (!scale || !plot) {
    return null;
  }
  const top = plot.y + LABEL_GAP / 2;
  const bottom = plot.y + plot.height - LABEL_GAP / 2;
  const placed = series
    .flatMap((one) => {
      const value = lastValue(data, one.key, bar);
      const y = value === null ? undefined : scale(bar ? value / 2 : value);
      return typeof y === "number"
        ? [{ name: one.name, y: Math.min(Math.max(y, top), bottom) }]
        : [];
    })
    .sort((a, b) => a.y - b.y);
  // Each a gap below the one above, at least, so none overlaps; then, from the bottom, each a gap
  // above the one below, so none is pushed out of the plot.
  for (const [at, label] of placed.entries()) {
    const above = placed[at - 1];
    if (above) {
      placed[at] = { name: label.name, y: Math.max(label.y, above.y + LABEL_GAP) };
    }
  }
  for (let at = placed.length - 1; at >= 0; at -= 1) {
    const label = placed[at];
    const below = placed[at + 1];
    if (label) {
      placed[at] = {
        name: label.name,
        y: Math.min(label.y, below ? below.y - LABEL_GAP : bottom),
      };
    }
  }
  return (
    <g>
      {placed.map((label) => (
        <text
          key={label.name}
          x={plot.x + plot.width + 6}
          y={label.y + 4}
          fill="var(--muted)"
          textAnchor="start"
        >
          {cut(label.name) !== label.name && <title>{label.name}</title>}
          {cut(label.name)}
        </text>
      ))}
    </g>
  );
}

/**
 * Bars per index, one series beside another, or, with `diverging`, the first series above the
 * baseline and the second below it, such as thumbs up and down, their values counts drawn apart:
 * the axis, the tooltip and the table show each as the count it is.
 */
export function BarChart({
  label,
  data,
  index,
  series,
  format = String,
  diverging = false,
  unknown = 0,
  tick,
}: {
  label: string;
  data: readonly Datum[];
  index: Index;
  series: readonly Series[];
  format?: (value: number) => string;
  diverging?: boolean;
  /** How many of the first rows are unknown, rather than empty: shaded, and named so. */
  unknown?: number;
  /** An index as the axis writes it, such as a date without its year; the rows keep it whole. */
  tick?: (index: string) => string;
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
  const fill = (at: number) => (at === 0 ? ink(0) : `url(#${id}-${at})`);
  return (
    <Figure label={label} index={index} series={drawn} data={data} shown={format}>
      <ResponsiveContainer>
        <RechartsBarChart
          data={[...rows]}
          stackOffset={diverging ? "sign" : "none"}
          barCategoryGap="20%"
          margin={{ top: 16, right: labelRoom(drawn), bottom: 0, left: 0 }}
        >
          <defs>
            {drawn.map((one, at) => at > 0 && <Hatch key={one.key} id={`${id}-${at}`} at={at} />)}
          </defs>
          <Axes index={index.key} shown={shown} tick={tick} />
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
              fill={fill(at)}
              stroke="var(--surface)"
              strokeWidth={2}
              radius={4}
              isAnimationActive={false}
              {...(diverging && { stackId: "sign" })}
            />
          ))}
          <DirectLabels data={rows} series={drawn} bar />
        </RechartsBarChart>
      </ResponsiveContainer>
    </Figure>
  );
}

/** A line per series over the index, such as a mean per day, with a gap where a day has none. */
export function LineChart({
  label,
  data,
  index,
  series,
  format = String,
  domain,
  unknown = 0,
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
}) {
  const drawn = series.slice(0, MAX_SERIES);
  return (
    <Figure label={label} index={index} series={drawn} data={data} shown={format} line>
      <ResponsiveContainer>
        <RechartsLineChart
          data={[...data]}
          margin={{ top: 16, right: labelRoom(drawn), bottom: 0, left: 0 }}
        >
          <Axes index={index.key} shown={format} domain={domain} />
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
              strokeDasharray={dash(at)}
              dot={{ r: 4, fill: ink(at), stroke: "var(--surface)", strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
          <DirectLabels data={data} series={drawn} />
        </RechartsLineChart>
      </ResponsiveContainer>
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
 * A whole in parts, as a donut beside a list of its parts, each with its value and share: the
 * largest three in the inks, solid, hatched one way, then the other, and the rest folded into
 * "Other", dotted in the muted ink. The list names every part in the donut; the figures are a
 * table beneath, as every chart's are.
 */
export function DonutChart({
  label,
  parts,
  format = String,
}: {
  label: string;
  parts: readonly Part[];
  format?: (value: number) => string;
}) {
  const id = useId();
  const caption = useId();
  const sorted = [...parts].filter((part) => part.value > 0).sort((a, b) => b.value - a.value);
  const rest = sorted.slice(MAX_SERIES).reduce((sum, part) => sum + part.value, 0);
  const shown: Part[] = [
    ...sorted.slice(0, MAX_SERIES),
    ...(rest > 0 ? [{ key: OTHER, name: "Other", value: rest }] : []),
  ];
  const total = shown.reduce((sum, part) => sum + part.value, 0);
  const share = (value: number) => `${Math.round((value / total) * 100)}%`;
  const fill = (at: number) => (at === 0 ? ink(0) : `url(#${id}-${at})`);
  return (
    <figure aria-labelledby={caption} className="flex flex-col gap-2">
      <figcaption id={caption} className="font-semibold text-fg text-sm">
        {label}
      </figcaption>
      <div className="flex flex-wrap items-center gap-6">
        <div className="size-40 shrink-0" aria-hidden="true">
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
                  <Cell key={part.key} fill={fill(at)} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  const part = payload[0];
                  return active && part && typeof part.value === "number" ? (
                    <div className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm shadow-md">
                      <span className="text-muted">{part.name}</span>{" "}
                      <span className="font-medium text-fg tabular-nums">
                        {format(part.value)} · {share(part.value)}
                      </span>
                    </div>
                  ) : null;
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex min-w-48 flex-1 flex-col gap-1.5 text-sm">
          {shown.map((part, at) => (
            <li key={part.key} className="flex items-center justify-between gap-4">
              <span className="inline-flex items-center gap-2 text-fg">
                <Swatch at={at} />
                {part.name}
              </span>
              <span className="text-muted tabular-nums">
                {format(part.value)} · {share(part.value)}
              </span>
            </li>
          ))}
        </ul>
      </div>
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
