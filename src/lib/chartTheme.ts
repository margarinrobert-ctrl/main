import type { CSSProperties } from "react";

/**
 * Shared chart theme — the single source of truth for every chart in the terminal
 * (recharts, lightweight-charts and hand-rolled SVG). Import from here instead of
 * hard-coding colors/styles so all charts read as one system.
 */

export const CHART = {
  /** Semantic market colors — the only green/red in the system. */
  call: "#34d399",
  put: "#f87171",
  /** Interactive accent + gradient partner. */
  accent: "#10b981",
  accentBright: "#34d399",
  cyan: "#22d3ee",
  /** Reserved series colors. */
  amber: "#fbbf24", // max pain
  violet: "#a78bfa", // gamma flip / HVL
  sky: "#7dd3fc", // IV / vol series
  /** Chrome. */
  text: "#a1a1aa",
  textDim: "#71717a",
  grid: "rgba(255,255,255,0.05)",
  axis: "rgba(255,255,255,0.14)",
  spot: "#e4e4e7",
} as const;

/** Axis tick styling for recharts (`tick={CHART_TICK}`). */
export const CHART_TICK = { fill: CHART.textDim, fontSize: 10 } as const;

/** Props shared by recharts X/Y axes. */
export const AXIS_PROPS = {
  stroke: CHART.axis,
  tickLine: false as const,
  axisLine: { stroke: CHART.axis },
  tick: CHART_TICK,
};

/** CartesianGrid props. */
export const GRID_PROPS = {
  stroke: CHART.grid,
  strokeDasharray: "3 6",
  vertical: false as const,
};

/** Tooltip content style (recharts `contentStyle`). */
export const TOOLTIP_STYLE: CSSProperties = {
  background: "rgba(9,10,14,0.94)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  boxShadow: "0 12px 32px -12px rgba(0,0,0,0.8)",
  fontSize: 11,
  padding: "8px 10px",
  backdropFilter: "blur(6px)",
};

export const TOOLTIP_LABEL_STYLE: CSSProperties = {
  color: "#e4e4e7",
  fontWeight: 600,
  marginBottom: 4,
};

export const TOOLTIP_ITEM_STYLE: CSSProperties = {
  color: "#a1a1aa",
  padding: "1px 0",
};

/** Cursor shown when hovering bar/area charts. */
export const TOOLTIP_CURSOR = { fill: "rgba(255,255,255,0.045)" } as const;
export const TOOLTIP_CURSOR_LINE = { stroke: "rgba(255,255,255,0.18)", strokeDasharray: "3 3" } as const;

/** Spread the trio onto a recharts <Tooltip {...TOOLTIP_PROPS}> for the standard look. */
export const TOOLTIP_PROPS = {
  contentStyle: TOOLTIP_STYLE,
  labelStyle: TOOLTIP_LABEL_STYLE,
  itemStyle: TOOLTIP_ITEM_STYLE,
} as const;

/** Reference-line label factory (spot / walls / flip markers). */
export function refLabel(value: string, fill: string, position: "insideTopRight" | "insideTopLeft" | "insideBottomRight" = "insideTopRight") {
  return { value, position, fill, fontSize: 10, fontWeight: 600 } as const;
}

/** lightweight-charts shared options (price/levels charts). */
export const LW_THEME = {
  layout: {
    background: { color: "transparent" },
    textColor: CHART.textDim,
    fontSize: 10,
  },
  grid: {
    vertLines: { color: "rgba(255,255,255,0.04)" },
    horzLines: { color: "rgba(255,255,255,0.04)" },
  },
  rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
  timeScale: { borderColor: "rgba(255,255,255,0.08)" },
  crosshair: {
    vertLine: { color: "rgba(16,185,129,0.4)", labelBackgroundColor: "#10b981" },
    horzLine: { color: "rgba(16,185,129,0.4)", labelBackgroundColor: "#10b981" },
  },
} as const;
