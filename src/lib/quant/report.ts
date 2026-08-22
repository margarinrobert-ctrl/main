import type { PerfSummary } from "./stats";

// Markdown rendering for study reports. Deliberately plain: a research report is read for its
// numbers and its caveats, and anything that makes a weak result look decorative is a liability.

export const pct = (x: number, dp = 1): string => (Number.isFinite(x) ? `${(x * 100).toFixed(dp)}%` : "n/a");
export const num = (x: number, dp = 2): string => (Number.isFinite(x) ? x.toFixed(dp) : x > 0 ? "inf" : "n/a");
export const usd = (x: number): string => (Number.isFinite(x) ? `${x < 0 ? "-" : ""}$${Math.abs(x).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "n/a");

export function table(headers: string[], rows: (string | number)[][]): string {
  const head = `| ${headers.join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((r) => `| ${r.map((c) => String(c)).join(" | ")} |`).join("\n");
  return [head, sep, body].join("\n");
}

export function summaryRow(label: string, s: PerfSummary): (string | number)[] {
  return [
    label,
    s.trades,
    pct(s.winRate, 1),
    num(s.grossEdgeTicks),
    num(s.costTicks),
    num(s.netEdgeTicks),
    num(s.profitFactor),
    num(s.sharpe),
    num(s.tStat),
    num(s.pValue, 3),
    usd(s.totalPnl),
    pct(s.maxDrawdownPct),
  ];
}

export const SUMMARY_HEADERS = [
  "strategy",
  "trades",
  "win",
  "gross (ticks)",
  "cost (ticks)",
  "net (ticks)",
  "PF",
  "Sharpe",
  "t (HAC)",
  "p",
  "P&L",
  "maxDD",
];

/** ASCII sparkline of a cumulative series — enough to see the shape without a chart dependency. */
export function sparkline(values: number[], width = 60): string {
  if (values.length < 2) return "";
  const chars = "▁▂▃▄▅▆▇█";
  const step = values.length / width;
  const sampled: number[] = [];
  for (let i = 0; i < width; i++) sampled.push(values[Math.min(values.length - 1, Math.floor(i * step))]);
  const lo = Math.min(...sampled);
  const hi = Math.max(...sampled);
  const span = hi - lo || 1;
  return sampled.map((v) => chars[Math.min(chars.length - 1, Math.floor(((v - lo) / span) * (chars.length - 1)))]).join("");
}

export const cumulative = (x: number[]): number[] => {
  let acc = 0;
  return x.map((v) => (acc += v));
};
