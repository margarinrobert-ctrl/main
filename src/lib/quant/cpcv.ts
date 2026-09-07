import { mean, std } from "./stats";

// Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric Cross-Validation —
// Bailey, Borwein, López de Prado & Zhu (2015).
//
// The question it answers is sharper than "is this strategy significant?". It is:
//
//     "When I use my selection procedure to pick a winner in-sample, how often does that winner
//      land in the BOTTOM HALF of the same candidate set out-of-sample?"
//
// If that probability is high, the procedure itself — not any particular configuration — is broken,
// and a better in-sample number is actively bad news. PBO above ~0.5 means the search is selecting
// noise; below ~0.2 means selection carries real information.

export interface PboResult {
  /** Probability that the in-sample winner underperforms the median out of sample. */
  pbo: number;
  /** Logit of the OOS relative rank of each in-sample winner, one per split. */
  logits: number[];
  /** OLS slope of OOS performance on IS performance across splits — the degradation line. */
  degradationSlope: number;
  /** Share of splits where the winner's OOS performance was outright negative. */
  oosLossRate: number;
  splits: number;
  candidates: number;
  blocks: number;
}

/** All combinations of `k` indices out of `n`, as index arrays. */
export function combinations(n: number, k: number): number[][] {
  const out: number[][] = [];
  const cur: number[] = [];
  const walk = (start: number) => {
    if (cur.length === k) {
      out.push([...cur]);
      return;
    }
    for (let i = start; i < n; i++) {
      cur.push(i);
      walk(i + 1);
      cur.pop();
    }
  };
  walk(0);
  return out;
}

const sharpeLike = (x: number[]): number => {
  const s = std(x);
  return s > 0 ? mean(x) / s : 0;
};

/**
 * @param series  one daily-P&L array per candidate configuration, all over the SAME days.
 * @param blocks  number of contiguous blocks (S in the paper). Must be even; 10-16 is typical.
 */
export function probabilityOfBacktestOverfitting(series: number[][], blocks = 10, score: (x: number[]) => number = sharpeLike): PboResult {
  const N = series.length;
  if (N < 2) throw new Error("PBO needs at least two candidate configurations");
  const T = series[0].length;
  const S = blocks % 2 === 0 ? blocks : blocks + 1;
  if (T < S * 4) throw new Error(`need at least ${S * 4} observations for ${S} blocks, have ${T}`);

  // Contiguous, equal-length blocks — contiguity is what keeps serial dependence inside a block.
  const size = Math.floor(T / S);
  const blockIdx: number[][] = [];
  for (let s = 0; s < S; s++) blockIdx.push(Array.from({ length: size }, (_, i) => s * size + i));

  const splits = combinations(S, S / 2);
  const logits: number[] = [];
  const isScores: number[] = [];
  const oosScores: number[] = [];
  let oosLosses = 0;

  for (const isBlocks of splits) {
    const isSet = new Set(isBlocks);
    const isRows = isBlocks.flatMap((b) => blockIdx[b]);
    const oosRows = blockIdx.filter((_, b) => !isSet.has(b)).flat();

    const isPerf = series.map((s) => score(isRows.map((i) => s[i])));
    const oosPerf = series.map((s) => score(oosRows.map((i) => s[i])));

    let bestIS = 0;
    for (let k = 1; k < N; k++) if (isPerf[k] > isPerf[bestIS]) bestIS = k;

    // Relative rank of the IS winner in the OOS ordering, in (0,1).
    const worse = oosPerf.filter((v) => v < oosPerf[bestIS]).length;
    const omega = Math.min(Math.max((worse + 0.5) / N, 1e-6), 1 - 1e-6);
    logits.push(Math.log(omega / (1 - omega)));
    isScores.push(isPerf[bestIS]);
    oosScores.push(oosPerf[bestIS]);
    if (oosPerf[bestIS] < 0) oosLosses++;
  }

  const mIS = mean(isScores);
  const mOOS = mean(oosScores);
  let cov = 0;
  let varIS = 0;
  for (let i = 0; i < isScores.length; i++) {
    cov += (isScores[i] - mIS) * (oosScores[i] - mOOS);
    varIS += (isScores[i] - mIS) ** 2;
  }

  return {
    pbo: logits.filter((l) => l <= 0).length / logits.length,
    logits,
    degradationSlope: varIS > 0 ? cov / varIS : 0,
    oosLossRate: oosLosses / splits.length,
    splits: splits.length,
    candidates: N,
    blocks: S,
  };
}
