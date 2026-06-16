import type { HistoryBar, OptionContract } from "../barchart/types";
import { atmIv, ivTermStructure, realizedVol } from "./analytics";

export type VolSide = "short-vol" | "long-vol" | "neutral" | "info";

export interface VolRead {
  side: VolSide;
  title: string;
  detail: string;
}

export interface VolReport {
  atmIv: number | null;
  rv10: number | null;
  rv20: number | null;
  vrpAbs: number | null; // IV - RV(20)
  vrpRatio: number | null; // IV / RV(20)
  termFront: number | null;
  termBack: number | null;
  termShape: "contango" | "backwardation" | "flat" | "n/a";
  skew: number | null; // 25-delta put IV - call IV
  reads: VolRead[];
}

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);

function skew25(chain: OptionContract[], expiration: string): number | null {
  const opts = chain.filter((c) => c.expiration === expiration && c.impliedVolatility != null && c.delta != null);
  const puts = opts.filter((c) => c.type === "put");
  const calls = opts.filter((c) => c.type === "call");
  if (!puts.length || !calls.length) return null;
  const put25 = puts.reduce((p, c) => (Math.abs(Math.abs(c.delta!) - 0.25) < Math.abs(Math.abs(p.delta!) - 0.25) ? c : p));
  const call25 = calls.reduce((p, c) => (Math.abs(c.delta! - 0.25) < Math.abs(p.delta! - 0.25) ? c : p));
  return put25.impliedVolatility! - call25.impliedVolatility!;
}

/**
 * Volatility-edge report: the volatility risk premium (ATM IV vs realized vol), the IV term
 * structure (contango/backwardation → IV-crush setups) and 25-delta skew, each translated into a
 * short-vol vs long-vol read. Standard vol-trading heuristics — educational, not advice.
 */
export function buildVolReport(chain: OptionContract[], spot: number | null, bars: HistoryBar[]): VolReport {
  const term = ivTermStructure(chain, spot).filter((x) => x.iv != null);
  const future = term.filter((x) => (x.dte ?? 0) >= 0);
  const front = future[0] ?? term[0] ?? null;
  const back = future[future.length - 1] ?? term[term.length - 1] ?? null;

  const iv = front?.iv ?? null;
  const rv10 = realizedVol(bars, 10);
  const rv20 = realizedVol(bars, 20);
  const base = rv20 ?? rv10;
  const vrpAbs = iv != null && base != null ? iv - base : null;
  const vrpRatio = iv != null && base ? iv / base : null;

  const termFront = front?.iv ?? null;
  const termBack = back?.iv ?? null;
  let termShape: VolReport["termShape"] = "n/a";
  if (termFront != null && termBack != null && front!.expiration !== back!.expiration) {
    const d = (termBack - termFront) / termFront;
    termShape = d > 0.03 ? "contango" : d < -0.03 ? "backwardation" : "flat";
  }

  const skew = front ? skew25(chain, front.expiration) : null;

  const reads: VolRead[] = [];

  if (vrpRatio != null) {
    if (vrpRatio >= 1.2) {
      reads.push({
        side: "short-vol",
        title: `Options RICH — VRP high (IV ${pct(iv)} vs RV ${pct(base)}, ${vrpRatio.toFixed(2)}×)`,
        detail:
          "Implied is well above realized → the volatility risk premium favors SELLING premium (delta-hedged short straddle/strangle, iron condor, credit spread). You collect theta and profit as IV reverts. Brutal left tail — size for the gap day, prefer defined risk.",
      });
    } else if (vrpRatio <= 0.95) {
      reads.push({
        side: "long-vol",
        title: `Options CHEAP — IV ≤ RV (IV ${pct(iv)} vs RV ${pct(base)}, ${vrpRatio.toFixed(2)}×)`,
        detail:
          "Implied is at/below realized → favors BUYING gamma (long straddle + delta-hedge / gamma scalp). You win if realized keeps outpacing implied; theta is the rent you pay while you wait.",
      });
    } else {
      reads.push({
        side: "neutral",
        title: `IV ≈ RV (IV ${pct(iv)} vs RV ${pct(base)})`,
        detail: "No strong volatility edge — trade direction/levels (Playbook) rather than vol here.",
      });
    }
  }

  if (termShape === "backwardation") {
    reads.push({
      side: "short-vol",
      title: `Backwardated term structure (front ${pct(termFront)} > back ${pct(termBack)})`,
      detail:
        "Front-month IV is elevated vs back — classic event/stress premium (earnings, macro). Selling front premium or a calendar (sell front / buy back) harvests the crush, but a binary gap through your strike is the risk.",
    });
  } else if (termShape === "contango") {
    reads.push({
      side: "info",
      title: `Contango term structure (back ${pct(termBack)} ≥ front ${pct(termFront)})`,
      detail: "Normal, calm regime — longer-dated vega is richer; back-month premium selling carries more vega risk.",
    });
  }

  if (skew != null) {
    if (skew > 0.03) {
      reads.push({
        side: "info",
        title: `Steep put skew (+${pct(skew)})`,
        detail:
          "Downside insurance is heavily bid (defensive/bearish hedging) — the fingerprint of the VRP. Plays: put-spread financing, or fade the richest puts within a defined-risk structure.",
      });
    } else if (skew < -0.01) {
      reads.push({
        side: "info",
        title: `Call skew (${pct(skew)})`,
        detail: "Calls bid over puts — upside speculation / squeeze tilt. Unusual for indices; more common in single-name momentum.",
      });
    }
  }

  reads.push({
    side: "info",
    title: "Reminder",
    detail:
      "Short-vol wins often and loses big; long-vol bleeds theta until it pays. IV/greeks are ~15-min delayed (CBOE), RV is from EOD closes. Educational — not financial advice.",
  });

  return { atmIv: iv, rv10, rv20, vrpAbs, vrpRatio, termFront, termBack, termShape, skew, reads };
}
