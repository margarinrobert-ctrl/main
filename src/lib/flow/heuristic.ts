import { flowThresholds, type FlowThresholds } from "../barchart/config";
import type { OptionContract } from "../barchart/types";

export interface FlowSignals {
  voir: number | null; // volume / open interest
  volSpike: number | null; // volume / trailing-avg volume
  notional: number | null; // volume * mid * 100 (USD)
  moneyness: number | null; // signed OTM-ness for the option's type
  mid: number | null;
}

export interface ScoredContract extends OptionContract {
  score: number; // 0..100
  flags: string[];
  signals: FlowSignals;
  passedGates: boolean;
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

function ramp(x: number, floor: number, cap: number): number {
  if (cap <= floor) return x >= cap ? 1 : 0;
  return clamp((x - floor) / (cap - floor), 0, 1);
}

function midPrice(c: OptionContract): number | null {
  if (c.bid !== null && c.ask !== null && c.bid >= 0 && c.ask > 0) return (c.bid + c.ask) / 2;
  if (c.last !== null && c.last > 0) return c.last;
  return null;
}

/** Signed OTM-ness: positive => out of the money for the given option type. */
function otmMoneyness(c: OptionContract): number | null {
  if (c.underlyingPrice === null || c.underlyingPrice <= 0) return null;
  const raw = (c.strike - c.underlyingPrice) / c.underlyingPrice;
  return c.type === "call" ? raw : -raw;
}

export interface ScoreOptions {
  avgVolume?: number | null;
  thresholds?: FlowThresholds;
}

/**
 * Score a single contract for "unusual activity" (0..100). Documented heuristic:
 *  gates: volume >= minVolume AND openInterest >= minOpenInterest
 *  signals (each ramped 0..1, then weighted): vol/OI, volume spike, notional, short-dated OTM.
 * If volume-spike data is missing (no history), its weight is redistributed so the
 * free tier isn't unfairly capped.
 */
export function scoreContract(c: OptionContract, opts: ScoreOptions = {}): ScoredContract {
  const t = opts.thresholds ?? flowThresholds;
  const mid = midPrice(c);
  const volume = c.volume ?? 0;
  const oi = c.openInterest ?? 0;

  const voir = oi > 0 ? volume / oi : null;
  const volSpike = opts.avgVolume && opts.avgVolume > 0 ? volume / opts.avgVolume : null;
  const notional = mid !== null ? volume * mid * 100 : null;
  const moneyness = otmMoneyness(c);
  const signals: FlowSignals = { voir, volSpike, notional, moneyness, mid };

  const passedGates = volume >= t.minVolume && oi >= t.minOpenInterest;
  if (!passedGates) {
    return { ...c, score: 0, flags: [], signals, passedGates: false };
  }

  const fVoir = voir === null ? 0 : ramp(voir, t.voirFloor, t.voirCap);
  const fSpike = volSpike === null ? 0 : ramp(volSpike, t.volSpikeFloor, t.volSpikeCap);
  const fNotional = notional === null ? 0 : ramp(notional, t.notionalFloor, t.notionalCap);
  const shortDte = c.dte !== null && c.dte <= t.shortDteDays;
  const farOtm = moneyness !== null && moneyness >= t.farOtmPct;
  const fDteOtm = shortDte && farOtm ? 1 : shortDte && moneyness !== null ? ramp(moneyness, 0, t.farOtmPct) : 0;

  const haveSpike = volSpike !== null;
  const wVoir = t.voirWeight;
  const wSpike = haveSpike ? t.volSpikeWeight : 0;
  const wNotional = t.notionalWeight;
  const wDteOtm = t.shortDteOtmWeight;
  const wSum = wVoir + wSpike + wNotional + wDteOtm;

  const score =
    wSum === 0
      ? 0
      : Math.round((100 * (wVoir * fVoir + wSpike * fSpike + wNotional * fNotional + wDteOtm * fDteOtm)) / wSum);

  const flags: string[] = [];
  if (voir !== null && voir >= t.voirFloor) flags.push("High Vol/OI");
  if (volSpike !== null && volSpike >= t.volSpikeFloor) flags.push("Volume Spike");
  if (notional !== null && notional >= t.notionalFloor) flags.push("Large Notional");
  if (shortDte && farOtm) flags.push("Short-dated OTM");

  return { ...c, score, flags, signals, passedGates: true };
}

/** Score and rank a set of contracts, highest score first. */
export function scoreContracts(contracts: OptionContract[], opts: ScoreOptions = {}): ScoredContract[] {
  return contracts.map((c) => scoreContract(c, opts)).sort((a, b) => b.score - a.score);
}
