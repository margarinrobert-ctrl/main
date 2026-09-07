import { mulberry32 } from "./rng";
import { maxDrawdown, mean } from "./stats";
import type { Trade } from "./types";

// Monte Carlo on the trade sequence. A backtest shows ONE ordering of the trades that happened to
// occur; the drawdown it displays is a single draw from a distribution. Resampling the trade list
// answers the question that actually determines whether a strategy is tradeable with real money:
// how deep does the drawdown get in the unlucky-but-normal case, and what fraction of orderings
// breach the account's pain threshold?

export interface MonteCarloResult {
  paths: number;
  /** Drawdown percentiles as a fraction of starting equity. */
  drawdownP50: number;
  drawdownP95: number;
  drawdownP99: number;
  /** Share of paths whose terminal equity is below the start. */
  probLoss: number;
  /** Share of paths that breach `ruinDrawdownPct` at any point. */
  probRuin: number;
  medianFinalPnl: number;
  p05FinalPnl: number;
  p95FinalPnl: number;
  /** Median number of consecutive losers across paths. */
  medianMaxLosingStreak: number;
}

export interface MonteCarloOptions {
  paths?: number;
  seed?: number;
  startEquity?: number;
  /** Drawdown fraction that counts as blowing up the account. */
  ruinDrawdownPct?: number;
  /** "shuffle" reorders the observed trades; "bootstrap" resamples them with replacement. */
  method?: "shuffle" | "bootstrap";
}

export function monteCarloTrades(trades: Trade[], opts: MonteCarloOptions = {}): MonteCarloResult {
  const paths = opts.paths ?? 5000;
  const start = opts.startEquity ?? 100_000;
  const ruin = opts.ruinDrawdownPct ?? 0.25;
  const method = opts.method ?? "shuffle";
  const rand = mulberry32(opts.seed ?? 20240);
  const pnls = trades.map((t) => t.pnl);
  const n = pnls.length;
  if (n < 5) {
    return { paths: 0, drawdownP50: 0, drawdownP95: 0, drawdownP99: 0, probLoss: 1, probRuin: 0, medianFinalPnl: 0, p05FinalPnl: 0, p95FinalPnl: 0, medianMaxLosingStreak: 0 };
  }

  const dds: number[] = [];
  const finals: number[] = [];
  const streaks: number[] = [];
  let losses = 0;
  let ruined = 0;

  for (let p = 0; p < paths; p++) {
    let seq: number[];
    if (method === "bootstrap") {
      seq = Array.from({ length: n }, () => pnls[Math.floor(rand() * n) % n]);
    } else {
      seq = [...pnls];
      for (let i = n - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [seq[i], seq[j]] = [seq[j], seq[i]];
      }
    }
    const equity = [start];
    let streak = 0;
    let maxStreak = 0;
    for (const v of seq) {
      equity.push(equity[equity.length - 1] + v);
      if (v <= 0) {
        streak++;
        if (streak > maxStreak) maxStreak = streak;
      } else streak = 0;
    }
    const dd = maxDrawdown(equity);
    dds.push(dd.pct);
    finals.push(equity[equity.length - 1] - start);
    streaks.push(maxStreak);
    if (equity[equity.length - 1] < start) losses++;
    if (dd.pct >= ruin) ruined++;
  }

  const pct = (arr: number[], q: number) => {
    const v = [...arr].sort((a, b) => a - b);
    return v[Math.min(v.length - 1, Math.max(0, Math.floor(q * (v.length - 1))))];
  };

  return {
    paths,
    drawdownP50: pct(dds, 0.5),
    drawdownP95: pct(dds, 0.95),
    drawdownP99: pct(dds, 0.99),
    probLoss: losses / paths,
    probRuin: ruined / paths,
    medianFinalPnl: pct(finals, 0.5),
    p05FinalPnl: pct(finals, 0.05),
    p95FinalPnl: pct(finals, 0.95),
    medianMaxLosingStreak: pct(streaks, 0.5),
  };
}

/** Mean per-trade P&L implied by the trade list — used by the cost-sensitivity break-even. */
export const perTradeMean = (trades: Trade[]): number => mean(trades.map((t) => t.pnl));
