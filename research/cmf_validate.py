"""Does CMF actually do anything, or is it the barrier geometry?

The forward test in cmf_maxai.py says the barriers-only reading of NQ34 makes $102,571 on data the
paper never saw. Before that means anything, three questions have to be answered:

  1. RANDOM-ENTRY NULL. A $900 stop against a $1,500 target breaks even at a 37.5% win rate, and
     the strategy wins 40.5%. Feed the SAME machinery random entry times and see what it pays. If
     the null pays the same, CMF contributes nothing and the result is the payoff asymmetry.
  2. WHERE the money is. Stop and target exits together LOSE $58,169; every dollar of profit comes
     from positions closed at 16:00. That is a different strategy from the one the paper describes.
  3. IS 0.25 SPECIAL, and is 20 bars special? A threshold that only works at one setting is a fit.

Usage: python3 research/cmf_validate.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
from cmf_maxai import (CMF_LEN, CMF_THRESH, COSTS, POINT_VALUE, RTH_END, RTH_START,
                       STOP_DOLLARS, TARGET_DOLLARS, cmf, load, simulate_hold)
from nqdata import minute_of_day


def nw_t(x, lag=20):
    x = np.asarray(x, float)
    n = len(x)
    if n < 20:
        return np.nan
    e = x - x.mean()
    s = (e @ e) / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return np.nan if s <= 0 else x.mean() / np.sqrt(s / n)


@njit(cache=True)
def sim_entries(o, h, l, c, sess, ent_mask, ent_side, stop_pts, target_pts, cost):
    """Take the given entries (one position at a time), exit at barrier or session close."""
    n = len(c)
    pos = 0
    entry = 0.0
    ent_i = -1
    t_side = np.zeros(n, np.int64); t_in = np.zeros(n, np.int64)
    t_pnl = np.zeros(n, np.float64); t_reason = np.zeros(n, np.int64)
    k = 0
    for i in range(1, n):
        new_sess = sess[i] != sess[i - 1]
        if pos != 0:
            if new_sess:
                t_side[k] = pos; t_in[k] = ent_i
                t_pnl[k] = pos * (o[i] - entry) * POINT_VALUE - cost; t_reason[k] = 3; k += 1
                pos = 0
            else:
                sp = entry - pos * stop_pts
                tp = entry + pos * target_pts
                hs = (l[i] <= sp) if pos == 1 else (h[i] >= sp)
                ht = (h[i] >= tp) if pos == 1 else (l[i] <= tp)
                if hs:
                    t_side[k] = pos; t_in[k] = ent_i
                    t_pnl[k] = -stop_pts * POINT_VALUE - cost; t_reason[k] = 1; k += 1
                    pos = 0
                elif ht:
                    t_side[k] = pos; t_in[k] = ent_i
                    t_pnl[k] = target_pts * POINT_VALUE - cost; t_reason[k] = 2; k += 1
                    pos = 0
        if pos == 0 and not new_sess and ent_mask[i - 1] == 1:
            pos = ent_side[i - 1]; entry = o[i]; ent_i = i
    if pos != 0:
        t_side[k] = pos; t_in[k] = ent_i
        t_pnl[k] = pos * (c[n - 1] - entry) * POINT_VALUE - cost; t_reason[k] = 3; k += 1
    return t_side[:k], t_in[:k], t_pnl[:k], t_reason[:k]


def main() -> None:
    seg, o, h, l, c, v, sess, m, sig = load()
    stop_pts = STOP_DOLLARS / POINT_VALUE
    tgt_pts = TARGET_DOLLARS / POINT_VALUE
    COST = COSTS["repo"]
    mod = minute_of_day(seg.index)

    side, ti, to, pnl, why = simulate_hold(o, h, l, c, sess, sig, stop_pts, tgt_pts, COST)
    print("=" * 104)
    print("1. THE RANDOM-ENTRY NULL — does CMF beat coin-flip entries into the same barriers?")
    print("=" * 104)
    print(f"\n  CMF rule: {len(pnl):,} trades, ${pnl.sum():,.0f}, ${pnl.mean():.2f}/trade, "
          f"win {100*(pnl>0).mean():.1f}%, NW t = {nw_t(pnl):.2f}")
    print(f"  break-even win rate for a ${STOP_DOLLARS:,.0f}/${TARGET_DOLLARS:,.0f} barrier: "
          f"{100*STOP_DOLLARS/(STOP_DOLLARS+TARGET_DOLLARS):.1f}%\n")

    # Null A: same entry BARS, random sides. Isolates direction from timing.
    # Null B: random entry bars (same count, same time-of-day distribution), sides drawn from the
    #         strategy's own long/short mix. Isolates timing from direction.
    rng = np.random.default_rng(20250822)
    n_ent = len(pnl)
    long_share = (side == 1).mean()
    ent_bars_real = np.zeros(len(c), np.int64)
    ent_bars_real[ti - 1] = 1

    for name, reps in (("A. same entry bars, RANDOM side", 400), ("B. RANDOM entry bars, same side mix", 400)):
        res = []
        for _ in range(reps):
            mask = np.zeros(len(c), np.int64)
            sd = np.zeros(len(c), np.int64)
            if name.startswith("A"):
                mask = ent_bars_real.copy()
                idx = np.where(mask == 1)[0]
                sd[idx] = np.where(rng.random(len(idx)) < long_share, 1, -1)
            else:
                idx = rng.choice(len(c) - 2, size=n_ent, replace=False)
                mask[idx] = 1
                sd[idx] = np.where(rng.random(len(idx)) < long_share, 1, -1)
            _, _, p, _ = sim_entries(o, h, l, c, sess, mask, sd, stop_pts, tgt_pts, COST)
            res.append(p.mean() if len(p) else np.nan)
        res = np.array(res)
        pct = 100 * (res < pnl.mean()).mean()
        print(f"  {name:<38} null $/trade  mean {res.mean():>8.2f}  sd {res.std():>7.2f}  "
              f"5th {np.percentile(res,5):>8.2f}  95th {np.percentile(res,95):>8.2f}   "
              f"CMF beats {pct:.1f}% of draws")

    print("\n" + "=" * 104)
    print("2. WHERE THE PROFIT IS — the barriers lose; the 16:00 flat is the whole edge")
    print("=" * 104 + "\n")
    print(f"  {'exit':<20}{'side':>7}{'n':>8}{'net $':>13}{'$/trade':>11}{'win%':>8}")
    for r, nm in ((1, "$900 stop"), (2, "$1,500 target"), (3, "16:00 session close")):
        for s, sn in ((1, "long"), (-1, "short")):
            msk = (why == r) & (side == s)
            if msk.sum():
                print(f"  {nm:<20}{sn:>7}{msk.sum():>8,}{pnl[msk].sum():>13,.0f}"
                      f"{pnl[msk].mean():>11.2f}{100*(pnl[msk]>0).mean():>7.1f}%")
    bar = why != 3
    print(f"\n  barrier exits only : {bar.sum():,} trades, ${pnl[bar].sum():,.0f} "
          f"(${pnl[bar].mean():.2f}/trade)")
    print(f"  16:00 exits only   : {(~bar).sum():,} trades, ${pnl[~bar].sum():,.0f} "
          f"(${pnl[~bar].mean():.2f}/trade)")
    ent_mod = mod[ti]
    print(f"\n  entry time-of-day of 16:00-exit trades: median {np.median(ent_mod[~bar]):.0f} min "
          f"({int(np.median(ent_mod[~bar]))//60:02d}:{int(np.median(ent_mod[~bar]))%60:02d} ET), "
          f"vs {np.median(ent_mod[bar]):.0f} for barrier exits")

    print("\n" + "=" * 104)
    print("3. IS 0.25 SPECIAL? IS 20 BARS SPECIAL?")
    print("=" * 104 + "\n")
    print(f"  {'CMF len':>8}{'thresh':>8}{'trades':>9}{'net $':>12}{'$/trade':>10}{'PF':>7}{'NW t':>7}")
    for length in (10, 20, 30, 60):
        mm = cmf(h, l, c, v, length)
        for th in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
            sg = np.where(np.isnan(mm), 0, np.where(mm >= th, 1, np.where(mm <= -th, -1, 0))).astype(np.int64)
            _, _, _, p, w = simulate_hold(o, h, l, c, sess, sg, stop_pts, tgt_pts, COST)
            if len(p) < 100:
                continue
            gp = p[p > 0].sum(); gl = -p[p < 0].sum()
            star = "  <- published" if (length == CMF_LEN and abs(th - CMF_THRESH) < 1e-9) else ""
            print(f"  {length:>8}{th:>8.2f}{len(p):>9,}{p.sum():>12,.0f}{p.mean():>10.2f}"
                  f"{(gp/gl if gl>0 else 0):>7.3f}{nw_t(p):>7.2f}{star}")


if __name__ == "__main__":
    main()
