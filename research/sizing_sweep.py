"""100,000+ position-sizing combinations on one strategy, judged the same way as everything else.

A warning that belongs at the top rather than in a footnote: **sizing creates no edge.** It
reshapes the distribution of an edge that either exists or does not. Sweeping 100,000 sizing
rules over 134 trades will absolutely find configurations that look spectacular, for the same
reason sweeping 4 million entry rules did. So:

  * every configuration is scored on the RESEARCH block and read once on the LOCKED block
  * the headline metric is risk-adjusted, not dollars, because leverage buys dollars for free
  * the report says what the median configuration does, not just the best one, since the gap
    between them is the size of the selection problem

Seven schemes are swept:

  fixed          one contract, always -- the baseline everything is measured against
  fixed risk     a constant DOLLAR risk per trade, no compounding
  fractional     a constant PERCENT of current equity at risk -- compounds
  inverse ATR    size inversely to the stop distance, so every trade risks the same
  vol target     size inversely to trailing realised volatility
  Kelly          fraction of the Kelly stake, estimated on RESEARCH ONLY
  equity filter  any of the above, muted while the equity curve is below its own moving average
"""
from __future__ import annotations

import itertools
import sys
import time

import numpy as np
from numba import njit, prange

sys.path.insert(0, "research")
from test_suite import build

PV = 2.0

SCHEMES = ["fixed", "fixed risk", "fractional", "inverse ATR", "vol target", "Kelly"]
RISK_PCT = [0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04]
VOL_LB = [20, 50, 100, 200]
VOL_MULT = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
MAX_LOTS = [1, 2, 3, 4, 5, 8, 10, 20, 999]
CAPITAL = [10_000.0, 25_000.0, 50_000.0, 100_000.0, 250_000.0]
EQ_FILTER = [0, 10, 20, 50]
STOPS = [2.0, 2.5, 3.0]        # sizing and stop distance interact, so the stop is swept too


@njit(cache=True)
def run_one(pnl1, risk_d, volf, sess, cut, n_sess,
            scheme, risk_pct, vol_mult, max_lots, cap0, eqma, kelly_f,
            out):
    """pnl1 = P&L per ONE contract; risk_d = dollar risk of the stop; volf = trailing vol factor."""
    eq = cap0
    peak = cap0
    dd = 0.0
    res_end = cap0
    n = len(pnl1)
    daily = np.zeros(n_sess)
    hist = np.zeros(n)
    nh = 0
    for i in range(n):
        lots = 1.0
        if scheme == 0:
            lots = 1.0
        elif scheme == 1:                       # constant dollar risk off the STARTING capital
            lots = (risk_pct * cap0) / max(risk_d[i], 1e-9)
        elif scheme == 2:                       # constant percent of CURRENT equity
            lots = (risk_pct * eq) / max(risk_d[i], 1e-9)
        elif scheme == 3:                       # inverse ATR, same thing anchored to capital
            lots = (risk_pct * cap0) / max(risk_d[i], 1e-9)
        elif scheme == 4:                       # inverse trailing realised volatility
            lots = (risk_pct * eq) / max(risk_d[i], 1e-9) * vol_mult / max(volf[i], 1e-6)
        else:                                   # Kelly fraction, f estimated on research only
            lots = (kelly_f * risk_pct * eq) / max(risk_d[i], 1e-9)
        if eqma > 0 and nh > eqma:
            m = 0.0
            for j in range(nh - eqma, nh):
                m += hist[j]
            m /= eqma
            if eq < m:
                lots = 0.0
        lots = np.floor(lots)
        if lots > max_lots:
            lots = max_lots
        if lots < 0.0:
            lots = 0.0
        p = pnl1[i] * lots
        eq += p
        hist[nh] = eq; nh += 1
        if eq > peak:
            peak = eq
        if peak - eq > dd:
            dd = peak - eq
        s = sess[i]
        if s < n_sess:
            daily[s] += p
        if s < cut:
            res_end = eq
        if eq <= cap0 * 0.05:                   # ruined; stop trading
            for j in range(i + 1, n):
                hist[nh] = eq; nh += 1
            break
    m = 0.0
    for i in range(n_sess):
        m += daily[i]
    m /= n_sess
    v = 0.0
    for i in range(n_sess):
        v += (daily[i] - m) * (daily[i] - m)
    v = np.sqrt(v / max(n_sess - 1, 1))
    out[0] = eq - cap0
    out[1] = dd
    out[2] = (m / v * np.sqrt(252.0)) if v > 0 else 0.0
    out[3] = res_end - cap0
    out[4] = eq - res_end
    out[5] = ((eq - cap0) / dd) if dd > 0 else 0.0
    out[6] = 1.0 if eq <= cap0 * 0.5 else 0.0


@njit(parallel=True, cache=True)
def bootstrap(pnl1, risk_d, volf, sess, cut, n_sess, grid, kelly_f, paths, seed, OUT):
    """The robustness test that matters for sizing: a compounding scheme is PATH DEPENDENT.
    Two orderings of the same trades give different equity curves, different drawdowns and
    different ruin outcomes. Rank by the 5th percentile across orderings, not by the one
    ordering history happened to deal."""
    n = len(pnl1)
    for g in prange(grid.shape[0]):
        sc = grid[g, 0]; rp = grid[g, 1]; lb = grid[g, 2]; vm = grid[g, 3]
        ml = grid[g, 4]; cp = grid[g, 5]; ef = grid[g, 6]
        nets = np.zeros(paths); dds = np.zeros(paths); ruin = 0.0
        np.random.seed(seed + g)
        out = np.zeros(7)
        for b in range(paths):
            idx = np.random.permutation(n)
            bp = pnl1[idx]; br = risk_d[idx]; bv = volf[idx]; bs = sess[idx]
            run_one(bp, br, bv, bs, cut, n_sess, int(sc), rp, vm, ml, cp, int(ef),
                    kelly_f, out)
            nets[b] = out[0]; dds[b] = out[1]; ruin += out[6]
        nets.sort(); dds.sort()
        OUT[g, 0] = nets[int(0.05 * paths)]
        OUT[g, 1] = nets[int(0.50 * paths)]
        OUT[g, 2] = dds[int(0.95 * paths)]
        OUT[g, 3] = ruin / paths


@njit(parallel=True, cache=True)
def sweep(pnl1, risk_d, VOLS, sess, cut, n_sess, grid, kelly_f, RES):
    for g in prange(grid.shape[0]):
        sc = grid[g, 0]; rp = grid[g, 1]; lb = grid[g, 2]; vm = grid[g, 3]
        ml = grid[g, 4]; cp = grid[g, 5]; ef = grid[g, 6]
        out = np.zeros(7)
        run_one(pnl1, risk_d, VOLS[int(lb)], sess, cut, n_sess,
                int(sc), rp, vm, ml, cp, int(ef), kelly_f, out)
        for k in range(7):
            RES[g, k] = out[k]


def build_grid():
    rows = []
    for si, sc in enumerate(SCHEMES):
        rps = [0.0] if sc == "fixed" else RISK_PCT
        lbs = range(len(VOL_LB)) if sc == "vol target" else [0]
        vms = VOL_MULT if sc == "vol target" else [1.0]
        for rp, lb, vm, ml, cp, ef in itertools.product(rps, lbs, vms, MAX_LOTS, CAPITAL, EQ_FILTER):
            rows.append((si, rp, lb, vm, ml, cp, ef))
    return np.array(rows, np.float64)


def prep(conds, side, am, tp, fl, tf):
    s = build(list(conds), side=side, atr_mult=am, tp_r=tp, flat_min=fl, tf=tf)
    from test_suite import sig_bar
    _sb = sig_bar(s)
    atr_ = s.bars["atr"][_sb]
    risk_d = am * atr_ * PV
    us = np.unique(s.bars["sess"])
    ret = np.r_[0.0, np.diff(s.bars["c"])]
    VOLS = np.zeros((len(VOL_LB), len(s.pnl)))
    for i, lb in enumerate(VOL_LB):
        rv = np.array([ret[max(0, b - lb):b].std() if b > lb else np.nan for b in _sb])
        VOLS[i] = np.nan_to_num(rv / np.nanmedian(rv), nan=1.0)
    r = s.ent_sess < s.cut
    p = s.pnl[r]
    w = (p > 0).mean()
    payoff = p[p > 0].mean() / max(-p[p <= 0].mean(), 1e-9)
    kelly = float(max(0.0, min(1.0, w - (1 - w) / max(payoff, 1e-9))))
    return s, risk_d, VOLS, len(us), kelly


def main(conds=("RSI14>70", "lower wick>50%"), side=1, tp=1.0, fl=0, tf=60,
         boot_top=5000, paths=400):
    t0 = time.time()
    grid = build_grid()
    print(f"{len(grid):,} sizing configurations x {len(STOPS)} stop widths = "
          f"{len(grid)*len(STOPS):,} combinations", flush=True)

    ALL = []
    for am in STOPS:
        s, risk_d, VOLS, n_sess, kelly = prep(conds, side, am, tp, fl, tf)
        sess = s.ent_sess.astype(np.int64)
        RES = np.zeros((len(grid), 7))
        sweep(s.pnl.astype(np.float64), risk_d.astype(np.float64), VOLS,
              sess, np.int64(s.cut), np.int64(n_sess), grid, kelly, RES)
        print(f"   stop {am}xATR: {len(s.pnl)} trades, Kelly f {kelly:.3f}, "
              f"{time.time()-t0:.0f}s", flush=True)
        ALL.append(dict(am=am, s=s, risk_d=risk_d, VOLS=VOLS, n_sess=n_sess,
                        kelly=kelly, RES=RES, sess=sess))

    # ---- robustness: bootstrap the trade ORDER for the best configurations on research -------
    print(f"\n   order-bootstrapping the top {boot_top:,} by research Sharpe, "
          f"{paths} orderings each...", flush=True)
    for A in ALL:
        RES = A["RES"]
        rank = np.argsort(-RES[:, 2])[:boot_top]          # research-block Sharpe
        sub = grid[rank]
        OUT = np.zeros((len(sub), 4))
        bootstrap(A["s"].pnl.astype(np.float64), A["risk_d"].astype(np.float64),
                  A["VOLS"][0], A["sess"], np.int64(A["s"].cut), np.int64(A["n_sess"]),
                  sub, A["kelly"], np.int64(paths), np.int64(7), OUT)
        A["rank"] = rank; A["BOOT"] = OUT
    print(f"   done, {time.time()-t0:.0f}s")
    np.savez_compressed("results/sizing/sizing.npz",
                        grid=grid, stops=np.array(STOPS),
                        **{f"RES{i}": A["RES"] for i, A in enumerate(ALL)},
                        **{f"BOOT{i}": A["BOOT"] for i, A in enumerate(ALL)},
                        **{f"RANK{i}": A["rank"] for i, A in enumerate(ALL)},
                        schemes=np.array(SCHEMES))
    return grid, ALL


if __name__ == "__main__":
    main()
