"""The nulls. With 31 trades in three years, no metric in the report above means anything until
it is scored against an entry that carries no information.

Three controls, each holding a different thing fixed:
  RANDOM BAR   the same sessions, the same side, the same 1 ATR stop / 1R / 2R geometry and the
               same liquidation, entered at a random post-opening-range bar. This prices the
               session selection and the exit machine and asks what the BREAKOUT adds.
  COIN SIDE    the strategy's own bars, side chosen at random. This asks whether the trend filter
               knows the direction.
  ALWAYS LONG  the same bars, always long. NQ rose 89% over this sample, so a rule free to pick a
               side picks long; this prices that drift.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_core as C   # noqa: E402
import orb_run as R    # noqa: E402


def line(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


def walk_set(D, sig_bar, side, atr, t_end, equity0=C.EQUITY0):
    e_bar, e_px, qty, q1, pnl, code, rmul, amb, eq = C._walk(
        sig_bar, side, atr, t_end, D["m1_o"], D["m1_h"], D["m1_l"], D["m1_c"], D["m1_mod"],
        float(equity0), float(C.RISK_PCT), C.POINT_VALUE, float(C.SPREAD), float(C.SLIP),
        float(C.FEE_PTS), float(C.STOP_ATR), C.LIQUIDATE, 1)
    return pnl[qty > 0], rmul[qty > 0]


if __name__ == "__main__":
    D = C.build("NQ")
    blk, _ = R.blocks_of(D)
    t, side_all = R.run(D)

    # rebuild the per-trade 1m entry bar / end bar so the controls use identical machinery
    tf = D["trade_tf"]
    liq = pd.DataFrame({"s": D["m1_sess"], "m": D["m1_mod"], "i": np.arange(len(D["m1_ts"]))})
    liq = liq[liq["m"] >= C.LIQUIDATE].groupby("s", sort=True)["i"].first()

    # every bar that COULD have been entered: after the opening range, in a traded session
    elig = (D["mod"] >= C.SESS_OPEN + C.RANGE_MIN) & ~D["in_range"]
    sess_of = D["sess"]
    rng = np.random.default_rng(11)

    def control(kind, n_draw=2000):
        out = np.zeros(n_draw)
        pool = {s: np.flatnonzero(elig & (sess_of == s)) for s in t["sess"].unique()}
        for d in range(n_draw):
            bars, sides, atrs, ends = [], [], [], []
            for _, row in t.iterrows():
                p = pool[row["sess"]]
                if len(p) == 0:
                    continue
                b = rng.choice(p) if kind == "bar" else row["sig_bar"]
                s = (1 if rng.random() < 0.5 else -1) if kind == "side" else \
                    (1 if kind == "long" else row["side"])
                close_t = pd.Timestamp(D["ts"][b]) + pd.Timedelta(minutes=tf)
                i0 = int(np.searchsorted(D["m1_ts"], np.datetime64(close_t), side="left"))
                lb = int(liq.get(row["sess"], -1))
                if lb < 0 or i0 > lb - 1 or i0 >= len(D["m1_ts"]):
                    continue
                bars.append(i0); sides.append(s); atrs.append(D["atr"][b]); ends.append(lb - 1)
            if not bars:
                continue
            pnl, _ = walk_set(D, np.array(bars, np.int64), np.array(sides, np.int64),
                              np.array(atrs), np.array(ends, np.int64))
            out[d] = pnl.mean() if len(pnl) else 0.0
        return out

    obs = t["net"].mean()
    line("A. THREE MATCHED CONTROLS, whole sample (n = %d trades)" % len(t))
    print(f"  {'control':14s}{'median':>12s}{'mean':>12s}{'5-95%':>24s}{'observed':>12s}{'p':>9s}")
    for kind, lab in (("bar", "random bar"), ("side", "coin-flip side"), ("long", "always long")):
        c = control(kind, 1500 if kind == "bar" else 1500)
        p = (c >= obs).mean()
        print(f"  {lab:14s}{np.median(c):12,.2f}{c.mean():12,.2f}"
              f"   [{np.quantile(c,0.05):+9,.2f}, {np.quantile(c,0.95):+9,.2f}]"
              f"{obs:12,.2f}{p:9.3f}")
    print("\n  p is the share of control draws that EQUAL OR BEAT the strategy. With 31 trades the")
    print("  control distribution is wide by construction, so a non-rejection here is a statement")
    print("  about the sample size as much as about the rule.")

    line("B. DAY-BLOCK BOOTSTRAP on the realised trades")
    for name, mask in list(blk.items()) + [("ALL", np.ones(len(D["c"]), bool))]:
        sess_b = np.unique(D["sess"][mask])
        tt = t[t["sess"].isin(sess_b)]
        if len(tt) < 3:
            print(f"  {name:16s} n={len(tt):3d}  too few trades to bootstrap")
            continue
        x = tt["net"].to_numpy()
        bs = np.array([rng.choice(x, len(x), replace=True).mean() for _ in range(5000)])
        print(f"  {name:16s} n={len(tt):3d}  mean {x.mean():+9,.2f}  "
              f"95% CI [{np.quantile(bs,0.025):+9,.2f}, {np.quantile(bs,0.975):+9,.2f}]  "
              f"P(mean<=0) {(bs <= 0).mean():.3f}")

    line("C. WHERE THE MONEY IS")
    x = np.sort(t["net"].to_numpy())[::-1]
    tot = x.sum()
    print(f"  net ${tot:,.0f} over {len(x)} trades")
    for k in (1, 3, 5):
        print(f"    the best {k} trade(s) supply {100*x[:k].sum()/tot if tot else float('nan'):8.1f}% of net "
              f"(${x[:k].sum():,.0f})")
    print(f"  best trade ${x[0]:,.0f}   worst ${x[-1]:,.0f}")
    yr = pd.DatetimeIndex(t["ts"]).year
    print("\n  by calendar year:")
    for y in sorted(set(yr)):
        m = yr == y
        print(f"    {y}   n {m.sum():3d}   net ${t['net'][m].sum():+9,.0f}   "
              f"expectancy ${t['net'][m].mean():+8,.2f}")
