/**
 * Futures Risk:Reward & hit-probability quant — a standalone bracket-trade analyzer.
 *
 * Nothing in here touches the options chain. It works purely from a trade's entry / stop / target,
 * a contract's tick economics, and (optionally) a volatility + drift view of the underlying.
 *
 * The core question — "what's the probability price tags my take-profit before my stop?" — is a
 * two-barrier first-passage problem. For a driftless (edge-free) market the answer is exact and
 * needs no volatility at all:
 *
 *        P(target first) = riskDistance / (riskDistance + rewardDistance)
 *
 * i.e. a tighter stop is hit more often, in exact proportion — which is *why* stretching R:R lowers
 * your hit-rate one-for-one and R:R alone can never manufacture edge. Hand the model a directional
 * drift and it re-prices that probability with the gambler's-ruin scale function; hand it a horizon
 * volatility and it adds finite-window touch probabilities (reflection principle).
 *
 * Educational tooling — not financial advice.
 */

// ── Standard normal (self-contained, no external deps) ─────────────────────────────────────────
// Abramowitz-Stegun 7.1.26 error function, ~1e-7 absolute accuracy — plenty for probabilities.
function erf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y =
    1 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t) * Math.exp(-x * x);
  return x >= 0 ? y : -y;
}

/** Standard-normal cumulative distribution Φ(x). */
export function normCdf(x: number): number {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

const clamp01 = (p: number): number => (p < 0 ? 0 : p > 1 ? 1 : p);
// exp with the argument clamped so barrier ratios can't overflow to Infinity/NaN. Beyond ±50 the
// resulting probability is within e^-50 (~2e-22) of 0 or 1, so the clamp is invisible in practice.
const sexp = (x: number): number => Math.exp(x < -50 ? -50 : x > 50 ? 50 : x);

export type Side = "long" | "short";

export interface ContractSpec {
  symbol: string;
  name: string;
  tickSize: number; // minimum price increment (points)
  tickValue: number; // $ per tick per contract
}

/** $ per 1.00 point of price movement, per contract. */
export function pointValue(spec: Pick<ContractSpec, "tickSize" | "tickValue">): number {
  return spec.tickSize > 0 ? spec.tickValue / spec.tickSize : 0;
}

/** Snap a price to the contract's tick grid. */
export function roundToTick(price: number, tickSize: number): number {
  if (!(tickSize > 0)) return price;
  return Math.round(price / tickSize) * tickSize;
}

/**
 * Common CME / ICE futures and their micros. `tickValue / tickSize` gives the $/point multiplier:
 * ES $50/pt, NQ $20/pt, CL $1,000/pt, GC $100/pt, etc.
 */
export const FUTURES: ContractSpec[] = [
  { symbol: "ES", name: "E-mini S&P 500", tickSize: 0.25, tickValue: 12.5 },
  { symbol: "MES", name: "Micro E-mini S&P 500", tickSize: 0.25, tickValue: 1.25 },
  { symbol: "NQ", name: "E-mini Nasdaq-100", tickSize: 0.25, tickValue: 5 },
  { symbol: "MNQ", name: "Micro E-mini Nasdaq-100", tickSize: 0.25, tickValue: 0.5 },
  { symbol: "YM", name: "E-mini Dow", tickSize: 1, tickValue: 5 },
  { symbol: "MYM", name: "Micro E-mini Dow", tickSize: 1, tickValue: 0.5 },
  { symbol: "RTY", name: "E-mini Russell 2000", tickSize: 0.1, tickValue: 5 },
  { symbol: "M2K", name: "Micro E-mini Russell 2000", tickSize: 0.1, tickValue: 0.5 },
  { symbol: "CL", name: "Crude Oil (WTI)", tickSize: 0.01, tickValue: 10 },
  { symbol: "MCL", name: "Micro Crude Oil", tickSize: 0.01, tickValue: 1 },
  { symbol: "GC", name: "Gold", tickSize: 0.1, tickValue: 10 },
  { symbol: "MGC", name: "Micro Gold", tickSize: 0.1, tickValue: 1 },
  { symbol: "SI", name: "Silver", tickSize: 0.005, tickValue: 25 },
  { symbol: "NG", name: "Natural Gas", tickSize: 0.001, tickValue: 10 },
  { symbol: "6E", name: "Euro FX", tickSize: 0.00005, tickValue: 6.25 },
  { symbol: "6B", name: "British Pound", tickSize: 0.0001, tickValue: 6.25 },
  { symbol: "ZB", name: "30-Year T-Bond", tickSize: 0.03125, tickValue: 31.25 },
  { symbol: "ZN", name: "10-Year T-Note", tickSize: 0.015625, tickValue: 15.625 },
  { symbol: "ZF", name: "5-Year T-Note", tickSize: 0.0078125, tickValue: 7.8125 },
  { symbol: "HG", name: "Copper", tickSize: 0.0005, tickValue: 12.5 },
];

export interface RRInput {
  side: Side;
  entry: number;
  stop: number;
  target: number;
  tickSize: number;
  tickValue: number; // $ per tick per contract
  contracts?: number; // default 1
  costPerContract?: number; // round-trip commission + fees, $ per contract
  slippageTicks?: number; // slippage per fill, in ticks (charged on both entry and exit)
  horizonSigma?: number | null; // 1σ price move over the trade's expected life, in points
  horizonDrift?: number | null; // expected net drift over that life, in points (signed, + = up)
  assumedWinRate?: number | null; // your own historical hit-rate 0..1 — overrides the model for EV
}

export type Verdict = "positive" | "fair" | "negative" | "invalid";
export type WinProbSource = "assumed" | "drift" | "driftless";

export interface RRResult {
  valid: boolean;
  reason: string | null;

  side: Side;
  pointValue: number;
  contracts: number;

  // distances
  riskPoints: number;
  rewardPoints: number;
  riskTicks: number;
  rewardTicks: number;

  // dollar economics for the whole position (net of costs)
  costTotal: number; // total $ friction, round trip
  riskDollars: number; // net loss if stopped (gross risk + costs)
  rewardDollars: number; // net gain if target hits (gross reward − costs)
  grossRR: number; // reward / risk, in points
  netRR: number; // reward$ / risk$, after costs

  breakevenWinRate: number; // hit-rate needed to break even after costs

  // probability of tagging the target before the stop (bracket / OCO runs until one fills)
  pTargetDriftless: number; // risk/(risk+reward) — the fair, edge-free probability
  pTargetDrift: number | null; // drift + vol adjusted (needs horizonSigma)

  // finite-horizon touch odds within the expected holding window (need horizonSigma)
  pTouchTarget: number | null;
  pTouchStop: number | null;
  pCloseBeyondTarget: number | null;

  // expectancy — winProb = assumedWinRate ?? pTargetDrift ?? pTargetDriftless
  winProb: number;
  winProbSource: WinProbSource;
  expectancyR: number; // in R multiples (1R = net risk)
  expectancyDollars: number; // per position
  edge: number; // winProb − breakevenWinRate
  kelly: number; // full-Kelly fraction on net odds (clamped to [0,1])
  verdict: Verdict;
}

function fail(side: Side, reason: string): RRResult {
  return {
    valid: false,
    reason,
    side,
    pointValue: 0,
    contracts: 0,
    riskPoints: 0,
    rewardPoints: 0,
    riskTicks: 0,
    rewardTicks: 0,
    costTotal: 0,
    riskDollars: 0,
    rewardDollars: 0,
    grossRR: 0,
    netRR: 0,
    breakevenWinRate: 0,
    pTargetDriftless: 0,
    pTargetDrift: null,
    pTouchTarget: null,
    pTouchStop: null,
    pCloseBeyondTarget: null,
    winProb: 0,
    winProbSource: "driftless",
    expectancyR: 0,
    expectancyDollars: 0,
    edge: 0,
    kelly: 0,
    verdict: "invalid",
  };
}

/**
 * Two-barrier first passage with drift (gambler's ruin, drift-adjusted). Favourable barrier at
 * +b, adverse at −a, both distances > 0, in the trade's favourable frame. `mu` is the favourable
 * drift and `sigma` the 1σ move, both over the same horizon. Returns P(reach +b before −a).
 *
 * Derived from the scale function s(x)=e^(−θx), θ=2μ/σ²:
 *   P = (1 − e^(θa)) / (e^(−θb) − e^(θa)),  →  a/(a+b) as θ→0.
 */
function ruinWithDrift(a: number, b: number, mu: number, sigma: number): number {
  if (!(sigma > 0)) return clamp01(a / (a + b));
  const theta = (2 * mu) / (sigma * sigma);
  if (Math.abs(theta) * (a + b) < 1e-9) return clamp01(a / (a + b));
  const ea = sexp(theta * a);
  const enb = sexp(-theta * b);
  const denom = enb - ea;
  if (Math.abs(denom) < 1e-300) return clamp01(a / (a + b));
  return clamp01((1 - ea) / denom);
}

/**
 * Probability the process reaches a barrier at signed level `L` within the horizon, for arithmetic
 * BM with drift `mu` and vol `sigma` (both over the whole horizon; t is normalised to 1). Upward
 * barrier when L>0 (running max), downward when L<0 (running min) — reflection principle.
 */
function touchProb(L: number, mu: number, sigma: number): number {
  if (!(sigma > 0)) return 0;
  if (L === 0) return 1;
  const theta = (2 * mu) / (sigma * sigma);
  if (L > 0) {
    return clamp01(normCdf((mu - L) / sigma) + sexp(theta * L) * normCdf((-L - mu) / sigma));
  }
  return clamp01(normCdf((L - mu) / sigma) + sexp(theta * L) * normCdf((L + mu) / sigma));
}

/**
 * Analyse a futures bracket trade: risk:reward, dollar economics, and the probability of tagging the
 * take-profit before the stop. See the module header for the model.
 */
export function computeTradeRR(input: RRInput): RRResult {
  const {
    side,
    entry,
    stop,
    target,
    tickSize,
    tickValue,
    contracts = 1,
    costPerContract = 0,
    slippageTicks = 0,
    horizonSigma = null,
    horizonDrift = null,
    assumedWinRate = null,
  } = input;

  // ── Validation ──
  for (const [name, v] of [
    ["entry", entry],
    ["stop", stop],
    ["target", target],
  ] as const) {
    if (!Number.isFinite(v)) return fail(side, `Enter a valid ${name} price.`);
  }
  if (!(tickSize > 0)) return fail(side, "Tick size must be greater than zero.");
  if (!(tickValue > 0)) return fail(side, "Tick value must be greater than zero.");
  if (!(contracts > 0)) return fail(side, "Contracts must be greater than zero.");

  if (side === "long") {
    if (!(target > entry)) return fail(side, "For a long, the target must be above entry.");
    if (!(stop < entry)) return fail(side, "For a long, the stop must be below entry.");
  } else {
    if (!(target < entry)) return fail(side, "For a short, the target must be below entry.");
    if (!(stop > entry)) return fail(side, "For a short, the stop must be above entry.");
  }

  const riskPoints = Math.abs(entry - stop);
  const rewardPoints = Math.abs(target - entry);
  if (!(riskPoints > 0)) return fail(side, "Stop is at entry — risk distance is zero.");
  if (!(rewardPoints > 0)) return fail(side, "Target is at entry — reward distance is zero.");

  const pv = pointValue({ tickSize, tickValue });
  const riskTicks = riskPoints / tickSize;
  const rewardTicks = rewardPoints / tickSize;

  // ── Dollar economics (net of round-trip friction) ──
  const costTotal = contracts * (costPerContract + 2 * Math.max(0, slippageTicks) * tickValue);
  const grossRewardDollars = rewardPoints * pv * contracts;
  const grossRiskDollars = riskPoints * pv * contracts;
  const rewardDollars = grossRewardDollars - costTotal;
  const riskDollars = grossRiskDollars + costTotal;
  const grossRR = rewardPoints / riskPoints;
  const netRR = rewardDollars / riskDollars;
  // Break-even hit-rate: p·reward$ = (1−p)·risk$  →  p = risk$/(risk$+reward$). If costs swamp the
  // reward the position can never break even, so pin it at 1.
  const breakevenWinRate = rewardDollars > 0 ? clamp01(riskDollars / (riskDollars + rewardDollars)) : 1;

  // ── Hit probabilities ──
  const pTargetDriftless = clamp01(riskPoints / (riskPoints + rewardPoints));

  const sigma = horizonSigma != null && Number.isFinite(horizonSigma) && horizonSigma > 0 ? horizonSigma : null;
  const drift = horizonDrift != null && Number.isFinite(horizonDrift) ? horizonDrift : 0;
  // In the trade's favourable frame, "up" = toward profit. A long profits when price rises, a short
  // when it falls, so the favourable drift flips sign for shorts.
  const favDrift = side === "long" ? drift : -drift;

  let pTargetDrift: number | null = null;
  let pTouchTarget: number | null = null;
  let pTouchStop: number | null = null;
  let pCloseBeyondTarget: number | null = null;
  if (sigma != null) {
    pTargetDrift = ruinWithDrift(riskPoints, rewardPoints, favDrift, sigma);
    pTouchTarget = touchProb(rewardPoints, favDrift, sigma); // favourable barrier at +reward
    pTouchStop = touchProb(-riskPoints, favDrift, sigma); // adverse barrier at −risk
    pCloseBeyondTarget = clamp01(normCdf((favDrift - rewardPoints) / sigma));
  }

  // ── Expectancy ──
  const hasAssumed = assumedWinRate != null && Number.isFinite(assumedWinRate) && assumedWinRate >= 0 && assumedWinRate <= 1;
  const driftMeaningful = pTargetDrift != null && Math.abs(favDrift) > 0;
  const winProb = hasAssumed ? (assumedWinRate as number) : driftMeaningful ? (pTargetDrift as number) : pTargetDriftless;
  const winProbSource: WinProbSource = hasAssumed ? "assumed" : driftMeaningful ? "drift" : "driftless";

  const expectancyDollars = winProb * rewardDollars - (1 - winProb) * riskDollars;
  const expectancyR = winProb * netRR - (1 - winProb);
  const edge = winProb - breakevenWinRate;
  const kelly = netRR > 0 ? clamp01(winProb - (1 - winProb) / netRR) : 0;

  const eps = 1e-9 * Math.max(1, riskDollars);
  const verdict: Verdict = expectancyDollars > eps ? "positive" : expectancyDollars < -eps ? "negative" : "fair";

  return {
    valid: true,
    reason: null,
    side,
    pointValue: pv,
    contracts,
    riskPoints,
    rewardPoints,
    riskTicks,
    rewardTicks,
    costTotal,
    riskDollars,
    rewardDollars,
    grossRR,
    netRR,
    breakevenWinRate,
    pTargetDriftless,
    pTargetDrift,
    pTouchTarget,
    pTouchStop,
    pCloseBeyondTarget,
    winProb,
    winProbSource,
    expectancyR,
    expectancyDollars,
    edge,
    kelly,
    verdict,
  };
}
