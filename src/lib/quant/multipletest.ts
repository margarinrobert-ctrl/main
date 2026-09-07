// Multiple-testing corrections. Testing 40 strategy/parameter combinations at p<0.05 yields two
// "significant" results on pure noise by construction; these two procedures are the minimum honest
// response. Holm controls the family-wise error rate (no false positives at all, conservative);
// Benjamini-Hochberg controls the false discovery rate (a bounded share of the keepers are false),
// which is the right trade-off for a research funnel that will re-validate survivors out of sample.

export interface TestRow {
  label: string;
  p: number;
}

export interface CorrectedRow extends TestRow {
  /** Benjamini-Hochberg adjusted p-value (q-value). */
  qBH: number;
  /** Holm-Bonferroni adjusted p-value. */
  pHolm: number;
  rejectBH: boolean;
  rejectHolm: boolean;
  rank: number;
}

export function correctMultiple(rows: TestRow[], alpha = 0.05): CorrectedRow[] {
  const m = rows.length;
  if (!m) return [];
  const order = rows.map((r, i) => ({ ...r, i })).sort((a, b) => a.p - b.p);

  // Benjamini-Hochberg, with the standard monotonicity enforcement from the largest p downwards.
  const q = new Array<number>(m);
  let running = 1;
  for (let k = m - 1; k >= 0; k--) {
    running = Math.min(running, (order[k].p * m) / (k + 1));
    q[k] = Math.min(1, running);
  }

  // Holm-Bonferroni, monotone from the smallest p upwards.
  const h = new Array<number>(m);
  let runH = 0;
  for (let k = 0; k < m; k++) {
    runH = Math.max(runH, order[k].p * (m - k));
    h[k] = Math.min(1, runH);
  }

  const out: CorrectedRow[] = order.map((r, k) => ({
    label: r.label,
    p: r.p,
    qBH: q[k],
    pHolm: h[k],
    rejectBH: q[k] <= alpha,
    rejectHolm: h[k] <= alpha,
    rank: k + 1,
  }));
  return out;
}
