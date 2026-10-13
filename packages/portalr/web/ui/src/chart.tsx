/**
 * Charts on Recharts, adapted from Tremor's BarChart, LineChart and DonutChart (Apache-2.0; see
 * NOTICE): only what admin draws, restyled to the kit's tokens. A chart's series take the inks in
 * order, as marks and never as text, three at most, and each has a pattern too, so colour is
 * never its only cue (portalr ADR-0021): solid, then hatched one way, then the other; or a line
 * solid, dashed, then dotted. Each series is named in a legend, and directly at its last point,
 * and the figures are a table beneath, for those who read them rather than look.
 */

import { type ReactNode, useId } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  Pie,
  PieChart,
  BarChart as RechartsBarChart,
  LineChart as RechartsLineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from "recharts";
import { Table } from "./table";

/** A row of a chart: its index, such as a day, and each series' value on it, or none. */
export type Datum = Readonly<Record<string, string | number | null>>;

/** One series of a chart: the key its values are under in each row, and its name. */
export interface Series {
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

/** A chart's frame: what it shows, as a figure's caption, and its figures as a table. */
function Figure({
  label,
  index,
  series,
  data,
  format,
  legend,
  children,
}: {
  label: string;
  index: { readonly key: string; readonly name: string };
  series: readonly Series[];
  data: readonly Datum[];
  format: (value: number) => string;
  legend: ReactNode;
  children: ReactNode;
}) {
  const caption = useId();
  return (
    <figure aria-labelledby={caption} className="flex flex-col gap-2">
      <figcaption id={caption} className="font-semibold text-fg text-sm">
        {label}
      </figcaption>
      {legend}
      <div className="h-64 w-full text-muted text-xs" aria-hidden="true">
        {children}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted">Show the figures</summary>
        <Table caption={label}>
          <thead>
            <tr>
              <th scope="col">{index.name}</th>
              {series.map((one) => (
                <th key={one.key} scope="col">
                  {one.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={String(row[index.key])}>
                <th scope="row">{row[index.key]}</th>
                {series.map((one) => {
                  const value = row[one.key];
                  return (
                    <td key={one.key} className="tabular-nums">
                      {typeof value === "number" ? format(Math.abs(value)) : "–"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </Table>
      </details>
    </figure>
  );
}

/** Each series' name beside its mark, as the chart draws it: its ink and its pattern. */
function Legend({
  series,
  swatch,
}: {
  series: readonly Series[];
  swatch: (at: number) => ReactNode;
}) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-muted text-xs">
      {series.map((one, at) => (
        <li key={one.key} className="inline-flex items-center gap-1.5">
          <svg aria-hidden="true" width="16" height="10" className="shrink-0">
            {swatch(at)}
          </svg>
          {one.name}
        </li>
      ))}
    </ul>
  );
}

/** Tremor's tooltip: the index, then each series' mark, name and value, in the kit's colours. */
function ChartTooltip({
  active,
  payload,
  label,
  series,
  format,
}: Pick<TooltipContentProps<number, string>, "active" | "payload" | "label"> & {
  series: readonly Series[];
  format: (value: number) => string;
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
                <span
                  aria-hidden="true"
                  className="size-2 shrink-0 rounded-xs"
                  style={{ background: ink(at) }}
                />
                {series[at]?.name ?? item.name}
              </span>
              <span className="font-medium text-fg tabular-nums">
                {typeof item.value === "number" ? format(Math.abs(item.value)) : "–"}
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
  format,
  domain,
}: {
  index: string;
  format: (value: number) => string;
  domain?: readonly [number, number] | undefined;
}) {
  return (
    <>
      <CartesianGrid stroke="var(--line)" vertical={false} />
      <XAxis
        dataKey={index}
        tickLine={false}
        axisLine={false}
        stroke="var(--muted)"
        fontSize={12}
        minTickGap={16}
      />
      <YAxis
        tickLine={false}
        axisLine={false}
        stroke="var(--muted)"
        fontSize={12}
        width={40}
        {...(domain && { domain: [...domain] })}
        tickFormatter={(value: number) => format(Math.abs(value))}
      />
    </>
  );
}

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

/** Where a label is drawn: a mark's corner, and its size, as Recharts gives them. */
interface Place {
  /** The index's value of the mark's row, such as its day: LabelList's `dataKey` is the index. */
  value?: unknown;
  x?: number | string | undefined;
  y?: number | string | undefined;
  width?: number | string | undefined;
  height?: number | string | undefined;
}

/**
 * The index's value of the last row a series has a value in, other than none or nothing. Labels
 * are matched by it, not by their position, as Recharts skips a bar of nothing.
 */
const lastOf = (data: readonly Datum[], index: string, key: string) =>
  data.findLast((row) => typeof row[key] === "number" && row[key] !== 0)?.[index];

/** A bar series' name beside its last bar, at the bar's middle, in the margin to its right. */
function barLabel(data: readonly Datum[], index: string, key: string, name: string) {
  const last = lastOf(data, index, key);
  return ({ value, x, y, width, height }: Place) => {
    if (
      last === undefined ||
      value !== last ||
      typeof x !== "number" ||
      typeof y !== "number" ||
      typeof width !== "number" ||
      typeof height !== "number"
    ) {
      return null;
    }
    return (
      <text
        x={x + width + 6}
        y={y + height / 2 + 4}
        fill="var(--muted)"
        fontSize={11}
        textAnchor="start"
      >
        {name}
      </text>
    );
  };
}

/**
 * Line series' names at their last points, in the margin to the right, each nudged down from the
 * one above where they'd overlap. Recharts draws the series in order, so the first one's label
 * starts each drawing afresh.
 */
function lineLabels(data: readonly Datum[], index: string, series: readonly Series[]) {
  const placed: number[] = [];
  return (key: string, name: string) => {
    const last = lastOf(data, index, key);
    return ({ value, x, y }: Place) => {
      if (last === undefined || value !== last || typeof x !== "number" || typeof y !== "number") {
        return null;
      }
      if (key === series[0]?.key) {
        placed.length = 0;
      }
      let at = y + 4;
      while (placed.some((other) => Math.abs(other - at) < 12)) {
        at += 12;
      }
      placed.push(at);
      return (
        <text x={x + 8} y={at} fill="var(--muted)" fontSize={11} textAnchor="start">
          {name}
        </text>
      );
    };
  };
}

/**
 * Bars per index, one series beside another, or stacked: with `diverging`, the first series
 * above the baseline and the second below it, such as thumbs up and down, their values given as
 * counts and drawn apart.
 */
export function BarChart({
  label,
  data,
  index,
  series,
  format = String,
  diverging = false,
}: {
  label: string;
  data: readonly Datum[];
  index: { readonly key: string; readonly name: string };
  series: readonly Series[];
  format?: (value: number) => string;
  diverging?: boolean;
}) {
  const id = useId();
  const pattern = (at: number) => `${id}-pattern-${at}`;
  const drawn = series.slice(0, MAX_SERIES);
  const rows = diverging
    ? data.map((row) => {
        const below = drawn[1];
        const value = below ? row[below.key] : null;
        return below && typeof value === "number" ? { ...row, [below.key]: -value } : row;
      })
    : data;
  const fill = (at: number) => (at === 0 ? ink(0) : `url(#${pattern(at)})`);
  const hatch = (at: number) => <Hatch id={pattern(at)} at={at} />;
  return (
    <Figure
      label={label}
      index={index}
      series={drawn}
      data={data}
      format={format}
      legend={
        <Legend
          series={drawn}
          swatch={(at) => (
            <>
              <defs>{at > 0 && hatch(at)}</defs>
              <rect width="16" height="10" rx="2" fill={fill(at)} />
            </>
          )}
        />
      }
    >
      <ResponsiveContainer>
        <RechartsBarChart
          data={[...rows]}
          stackOffset={diverging ? "sign" : "none"}
          barCategoryGap="20%"
          margin={{ top: 16, right: 88, bottom: 0, left: 0 }}
        >
          <defs>
            {drawn.map((one, at) => at > 0 && <Hatch key={one.key} id={pattern(at)} at={at} />)}
          </defs>
          <Axes index={index.key} format={format} />
          {diverging && <ReferenceLine y={0} stroke="var(--edge)" />}
          <Tooltip
            cursor={{ fill: "var(--wash)" }}
            content={(props) => <ChartTooltip {...props} series={drawn} format={format} />}
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
            >
              <LabelList
                dataKey={index.key}
                content={barLabel(rows, index.key, one.key, one.name)}
              />
            </Bar>
          ))}
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
}: {
  label: string;
  data: readonly Datum[];
  index: { readonly key: string; readonly name: string };
  series: readonly Series[];
  format?: (value: number) => string;
  /** The value axis's ends, such as [0, 1] for a rate; Recharts' own where none is given. */
  domain?: readonly [number, number];
}) {
  const drawn = series.slice(0, MAX_SERIES);
  const labelled = lineLabels(data, index.key, drawn);
  return (
    <Figure
      label={label}
      index={index}
      series={drawn}
      data={data}
      format={format}
      legend={
        <Legend
          series={drawn}
          swatch={(at) => (
            <line
              x1="0"
              y1="5"
              x2="16"
              y2="5"
              stroke={ink(at)}
              strokeWidth="2"
              strokeDasharray={dash(at)}
            />
          )}
        />
      }
    >
      <ResponsiveContainer>
        <RechartsLineChart data={[...data]} margin={{ top: 16, right: 88, bottom: 0, left: 0 }}>
          <Axes index={index.key} format={format} domain={domain} />
          <Tooltip
            cursor={{ stroke: "var(--edge)" }}
            content={(props) => <ChartTooltip {...props} series={drawn} format={format} />}
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
            >
              <LabelList dataKey={index.key} content={labelled(one.key, one.name)} />
            </Line>
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </Figure>
  );
}

/** One part of a whole: its name, and how much of it. */
export interface Part {
  readonly name: string;
  readonly value: number;
}

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
  const shown = [
    ...sorted.slice(0, MAX_SERIES),
    ...(rest > 0 ? [{ name: "Other", value: rest }] : []),
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
                  (part, at) => at > 0 && <Hatch key={part.name} id={`${id}-${at}`} at={at} />,
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
                  <Cell key={part.name} fill={fill(at)} />
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
            <li key={part.name} className="flex items-center justify-between gap-4">
              <span className="inline-flex items-center gap-2 text-fg">
                <svg aria-hidden="true" width="12" height="12" className="shrink-0">
                  <defs>{at > 0 && <Hatch id={`${id}-key-${at}`} at={at} />}</defs>
                  <rect
                    width="12"
                    height="12"
                    rx="2"
                    fill={at === 0 ? ink(0) : `url(#${id}-key-${at})`}
                  />
                </svg>
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
        <Table caption={label}>
          <thead>
            <tr>
              <th scope="col">Part</th>
              <th scope="col">Value</th>
              <th scope="col">Share</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((part) => (
              <tr key={part.name}>
                <th scope="row">{part.name}</th>
                <td className="tabular-nums">{format(part.value)}</td>
                <td className="tabular-nums">{share(part.value)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </details>
    </figure>
  );
}
