"""PHASE 1 -- does the raw sweep -> IFVG setup have any expectancy before optimisation?

A DECLARED BASELINE, chosen from the literature's own description rather than from a search:
    sweep      wick penetration >= 0.10 ATR with a close back inside
    entry      limit at the proximal IFVG boundary, 60 minutes to fill
    stop       max(1.0 x ATR(14), beyond the sweep extreme + 0.25 ATR)
    target     1.5 R
    no breakeven, no trail, no session filter, no chop filter
Every one of those is varied later. Phase 1 exists to find out whether there is anything to vary.

SPLIT 60 / 20 / 20 by session, chronological, declared once. Only TRAIN is read here.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
import indicators as I        # noqa: E402
import levels as LV           # noqa: E402
import setup as S             # noqa: E402
import engine as E            # noqa: E402

TRAIN, VALID = 0.60, 0.20


def splits(tday, bars):
    u = np.unique(tday)
    a, b = u[int(len(u) * TRAIN)], u[int(len(u) * (TRAIN + VALID))]
    t = tday[bars]
    return dict(train=t < a, valid=(t >= a) & (t < b), oos=t >= b)


def metrics(R, pnl, tday_of_trade, pv=None):
    """SCORED IN DOLLARS, NOT IN R. A structural stop placed beyond the sweep extreme can sit a few
    ticks from the entry, so risk collapses and R explodes: the smallest-risk quintile of the
    sweep-stop configuration reads +0.6741 R while LOSING 1.41 points per trade. `CLAUDE.md` records
    the same failure for a channel stop -- "94% of the apparent contribution is the denominator".
    Profit factor and expectancy are therefore computed from P&L, and R is reported beside them as a
    diagnostic only."""
    if len(R) < 20 or not (pnl < 0).any():
        return None
    eq = np.cumsum(pnl)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    days = np.unique(tday_of_trade)
    d = pd.Series(pnl).groupby(pd.Series(tday_of_trade)).sum()
    alld = np.arange(len(days))
    dz = d.reindex(days, fill_value=0.0).to_numpy()
    sd = dz.std(ddof=1)
    down = dz[dz < 0]
    w, lo = pnl[pnl > 0], pnl[pnl < 0]
    return dict(n=len(R), R=float(R.mean()), usd=float(pnl.mean()), net=float(pnl.sum()),
                pf=float(w.sum() / abs(lo.sum())), win=float((pnl > 0).mean()),
                avg_w=float(w.mean()), avg_l=float(lo.mean()),
                dd=dd, retdd=float(pnl.sum() / dd) if dd > 0 else np.nan,
                sharpe=float(dz.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan,
                sortino=float(dz.mean() / down.std(ddof=1) * np.sqrt(252))
                if len(down) > 1 and down.std(ddof=1) > 0 else np.nan,
                p90=float(np.percentile(pnl, 90)), p10=float(np.percentile(pnl, 10)))


def line(tag, m, extra=""):
    if m is None:
        return f"      {tag:<26} fewer than 20 trades"
    return (f"      {tag:<26} n {m['n']:>5}  $/trade {m['usd']:>+8.2f}  PF {m['pf']:>6.3f}  "
            f"win {m['win']:.3f}  Sharpe {m['sharpe']:>+6.2f}  DD ${m['dd']:>8.0f}  "
            f"net ${m['net']:>+9.0f}{extra}")


def hdr(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


if __name__ == "__main__":
    t0 = time.perf_counter()
    d = LV.load()
    atr1 = I.ema(I.true_range(d["h"], d["l"], d["c"]), 14)
    pools = S.build_pools(d)
    hdr("V36 PHASE 1 -- does the raw sweep -> IFVG setup have expectancy before any optimisation?")
    print("   baseline: wick sweep >=0.10 ATR + close back inside | limit at the proximal IFVG "
          "boundary,\n   60m to fill | stop max(1.0xATR14, sweep extreme +0.25 ATR) | target 1.5R "
          "| no BE, no trail,\n   no session or chop filter | real MNQ costs x1.44 | ONE live "
          "order | 1-minute path")

    ifv = {}
    for tf in (5, 15):
        r = S.htf_frame(d, tf)
        atr_tf = I.ema(I.true_range(r["h"], r["l"], r["c"]), 14)
        ifv[tf] = (r, S.find_ifvgs(r, S.find_fvgs(r, atr_tf)))

    rows = []
    for defn in S.SWEEP_DEFS:
        sw_l = S.find_sweeps(d, pools, +1, defn=defn, atr=atr1)
        sw_s = S.find_sweeps(d, pools, -1, defn=defn, atr=atr1)
        for tf in (5, 15):
            r, iv = ifv[tf]
            su = pd.concat([S.setups(d, +1, sw_l, iv, r, tf),
                            S.setups(d, -1, sw_s, iv, r, tf)], ignore_index=True)
            if not len(su):
                continue
            su = su.sort_values("inv_bar_1m").reset_index(drop=True)
            tr, info = E.run(d, su, su.atr.to_numpy(), entry="edge", stop="max",
                             stop_k=1.0, stop_buf=0.25, tp="R", tp_r=1.5, retest_bars=60)
            if not len(tr):
                continue
            sb = su.inv_bar_1m.to_numpy()[:len(tr)]
            blk = splits(d["tday"], tr.fill_bar.to_numpy())
            for name in ("train",):
                m = blk[name]
                mm = metrics(tr.R.to_numpy()[m], tr.pnl.to_numpy()[m],
                             d["tday"][tr.fill_bar.to_numpy()[m]])
                rows.append(dict(defn=defn, tf=tf, block=name, fill=info["fill_rate"],
                                 **(mm or {})))
    df = pd.DataFrame(rows)
    hdr("PHASE 1 RESULT -- TRAIN block only, all eight (sweep definition x entry timeframe) cells")
    print(f"   {'sweep def':<12}{'tf':>4}{'fill':>7}{'n':>6}{'R/trade':>10}{'PF':>7}{'win':>7}"
          f"{'Sharpe':>8}{'DD':>8}{'net R':>9}{'p10':>8}{'p90':>8}")
    for r_ in df.itertuples():
        print(f"   {r_.defn:<12}{r_.tf:>4}{r_.fill:>7.3f}{r_.n:>6}{r_.R:>+10.4f}{r_.pf:>7.3f}"
              f"{r_.win:>7.3f}{r_.sharpe:>+8.2f}{r_.dd:>8.1f}{r_.net:>+9.1f}{r_.p10:>+8.2f}"
              f"{r_.p90:>+8.2f}")
    print(f"\n   cells with PF > 1: {int((df.pf > 1).sum())} of {len(df)}   "
          f"mean R/trade {df.R.mean():+.4f}   best {df.R.max():+.4f}   worst {df.R.min():+.4f}")
    df.to_csv("research/v36/v36_phase1.csv", index=False)
    print(f"   elapsed {time.perf_counter() - t0:.0f}s")
