import type { HistoryBar } from "../barchart/types";

/**
 * HAR-RV — Corsi's (2009) Heterogeneous Auto-Regressive realized-volatility model.
 *
 * The documented workhorse for realized-vol forecasting: it beats most GARCH variants out of sample
 * precisely because vol is driven by traders acting on different horizons (daily / weekly / monthly).
 * We lack intraday prints, so each day's realized variance is estimated from the OHLC bar with the
 * Garman–Klass estimator (a high-frequency-free daily variance proxy far more efficient than close-close),
 * then regressed:
 *
 *     RV_{t+1} = c + β_d·RV_d(t) + β_w·RV_w(t) + β_m·RV_m(t) + ε
 *       RV_d = today's daily variance, RV_w = mean of last 5, RV_m = mean of last 22
 *
 * β are fit by OLS on the bar history (falls back to Corsi's canonical weights if the design is singular).
 * The forecast is annualized and compared to implied vol to isolate the variance risk premium (see vrp.ts).
 * Pure — no network/IO — so it is unit-tested.
 */

const TRADING_DAYS = 252;

export interface HarRv {
  forecastVol: number | null; // annualized forecast realized vol for the next period
  rvDaily: number | null; // latest annualized daily realized vol
  rvWeek: number | null; // trailing 5-day annualized RV
  rvMonth: number | null; // trailing 22-day annualized RV
  betas: { c: number; d: number; w: number; m: number } | null; // fitted (or fallback) HAR coefficients
  fitted: boolean; // true = OLS fit, false = canonical-weight fallback
  r2: number | null; // in-sample fit quality
  n: number; // rows used in the fit
}

const EMPTY: HarRv = { forecastVol: null, rvDaily: null, rvWeek: null, rvMonth: null, betas: null, fitted: false, r2: null, n: 0 };

/** Per-day variance via Garman–Klass (falls back to close-to-close squared log-return if OHLC is degenerate). */
function dailyVariance(b: HistoryBar, prevClose: number | null): number | null {
  const { open: o, high: h, low: l, close: c } = b;
  if (h > 0 && l > 0 && o > 0 && c > 0 && h >= l) {
    const lnHL = Math.log(h / l);
    const lnCO = Math.log(c / o);
    const gk = 0.5 * lnHL * lnHL - (2 * Math.LN2 - 1) * lnCO * lnCO;
    if (Number.isFinite(gk) && gk >= 0) return gk;
  }
  if (prevClose != null && prevClose > 0 && c > 0) {
    const r = Math.log(c / prevClose);
    return r * r;
  }
  return null;
}

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const annualize = (variance: number | null) => (variance == null || variance < 0 ? null : Math.sqrt(variance * TRADING_DAYS));

/** Solve a symmetric linear system A·x = b (A is n×n) via Gaussian elimination with partial pivoting. */
function solve(A: number[][], b: number[]): number[] | null {
  const n = b.length;
  const M = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col++) {
    let piv = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r;
    if (Math.abs(M[piv][col]) < 1e-12) return null; // singular
    [M[col], M[piv]] = [M[piv], M[col]];
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = M[r][col] / M[col][col];
      for (let k = col; k <= n; k++) M[r][k] -= f * M[col][k];
    }
  }
  return M.map((row, i) => row[n] / row[i]);
}

export function harRvForecast(bars: HistoryBar[]): HarRv {
  if (!bars || bars.length < 30) return { ...EMPTY, n: 0 };

  // 1) daily realized-variance series
  const rv: number[] = [];
  for (let i = 0; i < bars.length; i++) {
    const v = dailyVariance(bars[i], i > 0 ? bars[i - 1].close : null);
    if (v != null) rv.push(v);
  }
  if (rv.length < 30) return { ...EMPTY, n: 0 };

  const rvW = (t: number) => mean(rv.slice(Math.max(0, t - 4), t + 1)); // last 5 incl. t
  const rvM = (t: number) => mean(rv.slice(Math.max(0, t - 21), t + 1)); // last 22 incl. t

  // 2) build HAR design rows (need 22-day lookback; target is next-day RV)
  const X: number[][] = [];
  const y: number[] = [];
  for (let t = 21; t < rv.length - 1; t++) {
    X.push([1, rv[t], rvW(t), rvM(t)]);
    y.push(rv[t + 1]);
  }

  // 3) OLS via normal equations XᵀX β = Xᵀy; fall back to Corsi canonical weights if singular
  let betas = { c: 0, d: 0.35, w: 0.35, m: 0.28 };
  let fitted = false;
  if (X.length >= 8) {
    const p = 4;
    const XtX = Array.from({ length: p }, () => Array(p).fill(0));
    const Xty = Array(p).fill(0);
    for (let r = 0; r < X.length; r++) {
      for (let i = 0; i < p; i++) {
        Xty[i] += X[r][i] * y[r];
        for (let j = 0; j < p; j++) XtX[i][j] += X[r][i] * X[r][j];
      }
    }
    const sol = solve(XtX, Xty);
    // accept only a sane fit (no NaN, non-explosive persistence)
    if (sol && sol.every((v) => Number.isFinite(v)) && sol[1] + sol[2] + sol[3] < 1.3 && sol[1] + sol[2] + sol[3] > 0) {
      betas = { c: sol[0], d: sol[1], w: sol[2], m: sol[3] };
      fitted = true;
    }
  }

  // 4) in-sample R²
  let r2: number | null = null;
  if (y.length) {
    const yBar = mean(y);
    let ssRes = 0;
    let ssTot = 0;
    for (let r = 0; r < X.length; r++) {
      const pred = betas.c + betas.d * X[r][1] + betas.w * X[r][2] + betas.m * X[r][3];
      ssRes += (y[r] - pred) ** 2;
      ssTot += (y[r] - yBar) ** 2;
    }
    r2 = ssTot > 0 ? Math.max(0, 1 - ssRes / ssTot) : null;
  }

  // 5) forecast next-period variance from the latest components, clamp ≥ 0
  const T = rv.length - 1;
  const dLatest = rv[T];
  const wLatest = rvW(T);
  const mLatest = rvM(T);
  const fVar = Math.max(0, betas.c + betas.d * dLatest + betas.w * wLatest + betas.m * mLatest);

  return {
    forecastVol: annualize(fVar),
    rvDaily: annualize(dLatest),
    rvWeek: annualize(wLatest),
    rvMonth: annualize(mLatest),
    betas,
    fitted,
    r2,
    n: X.length,
  };
}
