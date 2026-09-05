"""The engineered-feature sweep on the best base we have, scored on SHARPE.

THE BASE, established in v17base.py rather than inherited: Donchian 55 entry / 20 exit, ADX(14)
>= 25, stop 2.5 x ATR(20), one unit, no take profit, LONG, market order at the next open, NQ 15m.
Research 333 trades +0.1680 R/trade PF 1.328 Sharpe 1.08; locked 174 trades +0.1356 PF 1.308
Sharpe 1.05. It is the only candidate whose research block is BETTER than its locked block while
both are strong, which is the right shape, and ADX >= 25 reproduces as the thing that earns it.

SHARPE IS COMPUTED OVER EVERY TRADING DAY IN THE BLOCK, zero-filled on days that did not trade.
Over traded days only, a filter is PAID for trading less: keep the twelve best days a year and the
ratio explodes while the account earns nothing. Zero-filling is what forces a filter to earn its
selectivity, and it is the reason the numbers here are lower than a per-trade table would show.

THE NULL IS A RANDOM FILTER OF THE SAME SELECTIVITY, compared on the same statistic. Total dollars
fails every restrictive condition and per-trade edge passes every one; Sharpe on all days is
neither, but it still moves with trade count, so it needs the same treatment.

MULTIPLICITY IS STATED FIRST. 252 conditions -- 21 features, six levels, both directions -- expect
about 13 passes at alpha 0.05. That is a deliberately smaller pool than V16's 2,167: the features
were chosen to describe what a breakout does NOT already say, not enumerated.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v17")
import indicators as I       # noqa: E402
import v16core as C          # noqa: E402
import v16phase2 as P2       # noqa: E402
import v17feat as F          # noqa: E402
import daily_trend as DT     # noqa: E402

SPEC = dict(entry_n=55, exit_n=20, atr_len=20, stop=2.5, adx=25.0)
TF = 15


def context(tf=TF, spec=SPEC):
    """Bars, ATR, channels, ADX, the causal daily trend, and a causal prior-day OHLC."""
    P = C.prep(tf, entry_n=spec["entry_n"], exit_n=spec["exit_n"], atr_len=spec["atr_len"])
    P["adx"] = I.adx_di(P["h"], P["l"], P["c"], 14)[0]
    ts = pd.to_datetime(P["b"]["ts"]).to_numpy().astype("datetime64[ns]")
    # ONE MAPPING FOR EVERYTHING DAILY, built here rather than through DT.on_bars, because that
    # helper's `known_at` column can arrive as an object array of Timestamps and searchsorting it
    # against datetime64 compares a Timestamp with an int. Both sides are cast explicitly.
    D, st, cont = DT.states()
    known = pd.to_datetime(D["known_at"]).to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(known, ts, side="left") - 1   # strictly BEFORE: a bar never sees its day
    ok = pos >= 0
    daily = {}
    for k, v in st.items():
        z = np.zeros(len(P["c"]), bool)
        z[ok] = np.nan_to_num(np.asarray(v, float)[pos[ok]], nan=0.0) > 0.5
        z[:300] = False
        daily[k] = z
    for k, v in cont.items():
        z = np.full(len(P["c"]), np.nan)
        z[ok] = np.asarray(v, float)[pos[ok]]
        daily[k] = z
    for k, col in (("pdc", "c"), ("pdh", "h"), ("pdl", "l")):
        z = np.full(len(P["c"]), np.nan)
        z[ok] = D[col].to_numpy(float)[pos[ok]]
        P[k] = z
    res, lock, _ = P2.block_masks(P)
    return P, daily, res, lock


def base_signals(P, block, spec=SPEC, side=1):
    sig_all = C.signals(P, side)
    m = block[sig_all] & (np.nan_to_num(P["adx"][sig_all], nan=-1.0) >= spec["adx"])
    return sig_all[m]


def evaluate(P, O, idx, block):
    d = daily_series(P, O, idx, block)
    p = d.to_numpy()
    r = O["R"][idx] if len(idx) else np.array([0.0])
    eq = p.cumsum()
    dd = float((np.maximum.accumulate(eq) - eq).max())
    return dict(n=len(idx), R=float(p.sum()), perR=float(r.mean()) if len(idx) else np.nan,
                pf=float(r[r > 0].sum() / abs(r[r < 0].sum())) if (r < 0).any() else np.nan,
                win=float((r > 0).mean()) if len(idx) else np.nan,
                sharpe=float(p.mean() / p.std(ddof=1) * np.sqrt(252)) if p.std(ddof=1) > 0 else np.nan,
                dd=dd, retdd=float(p.sum() / dd) if dd > 0 else np.nan)


def daily_series(P, O, idx, block):
    days = np.unique(P["sess"][block])
    s = pd.Series(0.0, index=days)
    if len(idx):
        got = pd.Series(O["R"][idx]).groupby(P["sess"][O["sig"][idx]]).sum()
        s.loc[got.index] = got.to_numpy()
    return s


@njit(cache=True)
def _draw_sets(n, k, draws, seed, out):
    np.random.seed(seed)
    order = np.arange(n)
    for d in range(draws):
        for q in range(k):
            j = q + np.int64(np.random.random() * (n - q))
            tmp = order[q]; order[q] = order[j]; order[j] = tmp
        for q in range(k):
            out[d, q] = order[q]


def control(P, O, block, k, draws=300, seed=11):
    """`draws` random filters keeping exactly k signals, each locked and scored the same way."""
    n = len(O["sig"])
    if k < 5 or k > n:
        return np.array([]), np.array([])
    sets = np.empty((draws, k), np.int64)
    _draw_sets(n, k, draws, seed + k, sets)
    sh = np.empty(draws)
    rr = np.empty(draws)
    for d in range(draws):
        keep = np.zeros(n, bool)
        keep[sets[d]] = True
        idx = C.take(O, keep)
        s = evaluate(P, O, idx, block)
        sh[d] = s["sharpe"] if np.isfinite(s["sharpe"]) else -9.0
        rr[d] = s["R"]
    return sh, rr


if __name__ == "__main__":
    P, daily, res, lock = context()
    pool = F.build(P, entry_n=SPEC["entry_n"], daily=daily)
    conds = F.conditions(pool)
    sig = base_signals(P, res)
    O = C.outcomes(P, 1, sig, stop_mult=SPEC["stop"], tp_r=0.0)
    base = evaluate(P, O, C.take(O, np.ones(len(sig), bool)), res)
    print("=" * 112)
    print("V17 -- 21 engineered features on the V11 base, NQ 15m long, RESEARCH block")
    print("=" * 112)
    print(f"   base: {base['n']} trades  {base['R']:+.1f}R  {base['perR']:+.4f}/trade  "
          f"PF {base['pf']:.3f}  Sharpe {base['sharpe']:.2f}  maxDD {base['dd']:.1f}R")
    print(f"   {len(pool)} features x 6 levels x 2 directions = {len(conds)} conditions; "
          f"{0.05*len(conds):.0f} expected to pass at alpha 0.05 by chance\n")
    rows = []
    cache = {}
    for cname, score, lvl, direction in conds:
        keep = F.mask_for(score[sig], lvl, direction)
        k = int(keep.sum())
        if k < 30 or k == len(sig):
            continue
        idx = C.take(O, keep)
        s = evaluate(P, O, idx, res)
        if k not in cache:
            cache[k] = control(P, O, res, k)
        csh, crr = cache[k]
        if len(csh) == 0:
            continue
        rows.append(dict(cond=cname, feat=cname.split(" ")[0], dirn=cname.split(" ")[1],
                         lvl=lvl, keepk=k, **{q: s[q] for q in
                                              ("n", "R", "perR", "pf", "win", "sharpe", "dd", "retdd")},
                         ctl_sh=float(np.median(csh)), ctl_R=float(np.median(crr)),
                         p_sh=float((csh >= s["sharpe"]).mean()),
                         p_R=float((crr >= s["R"]).mean())))
    df = pd.DataFrame(rows)
    df.to_csv("results/v17/v17_sweep.csv", index=False)
    print(f"   {len(df)} conditions scorable (>= 30 trades kept)\n")
    print("=" * 112)
    print("A. HOW MANY BEAT A RANDOM FILTER OF THE SAME SELECTIVITY ON SHARPE")
    print("=" * 112)
    print(f"   observed p <= 0.05 : {int((df.p_sh <= 0.05).sum())} of {len(df)}")
    print(f"   expected by chance : {0.05*len(df):.1f}")
    print(f"   and on net R       : {int((df.p_R <= 0.05).sum())}")
    print("\n" + "=" * 112)
    print("B. BY FAMILY -- marginal averages, never the best cell")
    print("=" * 112)
    df["family"] = df.feat.str[0]
    LAB = {"A": "A breakout anatomy", "B": "B channel geometry", "C": "C higher timeframe",
           "D": "D volatility regime", "E": "E path structure"}
    g = df.groupby("family").agg(tests=("p_sh", "size"), med_p=("p_sh", "median"),
                                 rate=("p_sh", lambda x: float((x <= 0.05).mean())),
                                 med_sh=("sharpe", "median"), best_p=("p_sh", "min"))
    print(f"   {'family':<22}{'tests':>7}{'median p':>11}{'pass@.05':>11}"
          f"{'median Sharpe':>16}{'best p':>9}")
    for k, r in g.sort_values("rate", ascending=False).iterrows():
        print(f"   {LAB.get(k, k):<22}{int(r.tests):>7}{r.med_p:>11.3f}{r.rate:>10.1%}"
              f"{r.med_sh:>16.2f}{r.best_p:>9.3f}")
    print("\n" + "=" * 112)
    print("C. THE LEADERS ON RESEARCH -- read the ladders in phase 2 before believing any of them")
    print("=" * 112)
    top = df.sort_values("p_sh").head(20)
    print(f"   {'condition':<28}{'trades':>8}{'net R':>9}{'R/trade':>9}{'PF':>7}{'Sharpe':>8}"
          f"{'ctl Shp':>9}{'maxDD':>8}{'p Shp':>8}{'p R':>7}")
    for _, r in top.iterrows():
        print(f"   {r.cond:<28}{int(r.n):>8}{r.R:>+9.1f}{r.perR:>+9.4f}{r.pf:>7.3f}"
              f"{r.sharpe:>8.2f}{r.ctl_sh:>9.2f}{r.dd:>8.1f}{r.p_sh:>8.4f}{r.p_R:>7.3f}")
