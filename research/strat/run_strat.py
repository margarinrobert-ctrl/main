"""The Strat combo engine on US30, US100 and NQ: as configured, by block, by year, by side,
against a random-trigger control, then the knobs that decide it -- the location filter and
its point scale, the take-profit ratio, each combo family alone, the entry buffer, the
timeframe, and cost."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from strat import strat_core as SC  # noqa: E402

OUT = "results/strat"
os.makedirs(OUT, exist_ok=True)


def masks(market, dates):
    d = pd.DatetimeIndex(dates)
    if market == "NQ":
        cut = int(len(d) * 0.65)
        r = np.zeros(len(d), np.int64); r[:cut] = 1
        k = np.zeros(len(d), np.int64); k[cut:] = 1
        return {"research": r, "locked": k}
    return {"research": (d < "2022-01-01").astype(np.int64),
            "validation": ((d >= "2022-01-01") & (d < "2024-01-01")).astype(np.int64),
            "test": (d >= "2024-01-01").astype(np.int64)}


def line(label, t):
    m = SC.metrics(t)
    if m["n"] == 0:
        return f"  {label:<40} n    0"
    return (f"  {label:<40} n {m['n']:>5}  R {m['R']:+.4f}  PF {m['pf']:.3f}  win {m['win']:.1%}"
            f"  pts {m['pts']:+7.2f}  DD {m['dd']:6.1f}R  TP {m['tp_share']:.0%}"
            f"  fill-bar exit {m['fillbar']:.0%}  amb {m['amb']:.1%}  hold {m['hold']:.0f}")


def main():
    print("=" * 100)
    print("THE STRAT COMBO ENGINE (3-2 / 1-3-2 / 2-1-2 / 3-1-2 reversals, hammer bonus, location")
    print("score >= 2, stop order 20 pts past the trigger, SL 20 pts past the other side, TP 2R,")
    print("one trade at a time) -- 15-minute bars, US30 / US100 / NQ. Point = 0.1 on the CFD"
          " feeds,")
    print("0.25 on NQ. Nothing was fitted here; every block is out of sample for the parameters.")
    print("=" * 100)
    keep = {}
    for mk in SC.MARKETS:
        S = SC.Strat(mk, "15min")
        sig, up, dn = S.signals()
        score, flags = S.location(sig)
        ok = score >= S.P["min_loc"]
        M = masks(mk, S.F["dates"])
        trig = sig != 0
        d0, d1 = S.F["dates"][0], S.F["dates"][-1]
        print(f"\n{mk}: {S.F['n']:,} bars {d0:%Y-%m-%d} to {d1:%Y-%m-%d}."
              f" Combo triggers {int(trig.sum()):,} ({trig.mean():.2%} of bars), long "
              f"{int((sig > 0).sum())} / short {int((sig < 0).sum())}; location >= 2 on "
              f"{(ok & trig).sum() / trig.sum():.1%} of them (fractal "
              f"{np.mean((flags[trig] & 1) > 0):.0%},"
              f" PMG {np.mean((flags[trig] & 2) > 0):.0%}, reclaim "
              f"{np.mean((flags[trig] & 4) > 0):.0%},"
              f" HTF {np.mean((flags[trig] & 8) > 0):.0%})")
        # combo mix
        cnt = {}
        for name, w in (("3-2", S.P["w32"]), ("1-3-2", S.P["w132"]), ("2-1-2", S.P["w212"]),
                        ("3-1-2", S.P["w312"])):
            P1 = dict(S.P); P1.update(w32=0, w132=0, w212=0, w312=0, w_hs=0)
            P1[{"3-2": "w32", "1-3-2": "w132", "2-1-2": "w212", "3-1-2": "w312"}[name]] = 10
            s1, _, _ = S.signals(P1)
            cnt[name] = int((s1 != 0).sum())
        print("  combo occurrences (each alone, any score): "
              + ", ".join(f"{k} {v}" for k, v in cnt.items()))
        t_all = S.run(sig, ok)
        print(line("AS CONFIGURED, whole file", t_all))
        for blk, m in M.items():
            print(line(f"  block {blk}", S.run(sig, ok, m)))
        print(line("  long only", t_all[t_all.side > 0]))
        print(line("  short only", t_all[t_all.side < 0]))
        t_all["year"] = pd.DatetimeIndex(S.F["dates"])[t_all.trig].year
        g = t_all.groupby("year").agg(n=("r", "size"), R=("r", "mean"),
                                      win=("r", lambda x: (x > 0).mean()))
        print("  per year: " + "  ".join(f"{y}: {r.R:+.3f} ({r.n:.0f})" for y, r in g.iterrows()))
        # exit split
        for reason, lab in ((1, "stop"), (2, "target")):
            sub = t_all[t_all.reason == reason]
            print(f"  exit {lab:<7} n {len(sub):>5}  mean R {sub.r.mean():+.3f}  sum R "
                  f"{sub.r.sum():+.1f}")
        # control, whole file
        ctl, cnt_c, _ = SC.control(S, sig, ok, np.ones(S.F["n"], np.int64), n_draws=300)
        obs = t_all.r.mean()
        print(f"  random-trigger control (300 draws, {cnt_c:.0f} trades/draw vs {len(t_all)},"
              f" same order,"
              f" buffers, stop, 2R, lock): mean R {np.mean(ctl):+.4f} median {np.median(ctl):+.4f};"
              f" P(control >= strategy) {np.mean(ctl >= obs):.3f}")
        print(line("  no location filter at all", S.run(sig, np.ones(S.F["n"], bool))))
        print(line("  location >= 4 (fractal AND pmg, or all)", S.run(sig, score >= 4)))
        keep[mk] = (S, sig, ok, score, flags, t_all)
        t_all.to_csv(f"{OUT}/trades_{mk}_15m.csv", index=False)

    print("\n" + "=" * 100)
    print("LADDERS (whole file, 15m, R per trade / trades / PF)")
    print("=" * 100)
    print("\nPoint scale of every tolerance and buffer (x0.5 .. x10; x1 = the EA's 0.1 / 0.25"
          " point):")
    for mk, (S, sig, ok, score, flags, t_all) in keep.items():
        cells = []
        for sc in (0.5, 1.0, 2.0, 5.0, 10.0):
            sc_score, _ = S.location(sig, scale=sc)
            P = dict(S.P); P["entry_buf"] = S.P["entry_buf"] * sc; P["sl_buf"] = S.P["sl_buf"] * sc
            t = S.run(sig, sc_score >= S.P["min_loc"], P=P)
            m = SC.metrics(t)
            cells.append(f"x{sc:<4g} {m['R']:+.3f}/{m['n']}/{m['pf']:.2f}")
        print(f"  {mk:<6} " + "   ".join(cells))
    print("\nTake-profit ratio (RR 1 / 1.5 / 2 / 3 / 4), configured location:")
    for mk, (S, sig, ok, score, flags, t_all) in keep.items():
        cells = []
        for rr in (1.0, 1.5, 2.0, 3.0, 4.0):
            P = dict(S.P); P["rr"] = rr
            t = S.run(sig, ok, P=P)
            m = SC.metrics(t)
            be = 1.0 / (1.0 + rr)
            cells.append(f"RR{rr:<3g} {m['R']:+.3f}/{m['n']}/win {m['win']:.0%} (be {be:.0%})")
        print(f"  {mk:<6} " + "   ".join(cells))
    print("\nEach combo family alone (weight 10, others 0, hammer 0), configured location:")
    for mk, (S, sig, ok, score, flags, t_all) in keep.items():
        cells = []
        for name, key in (("3-2", "w32"), ("1-3-2", "w132"), ("2-1-2", "w212"), ("3-1-2", "w312")):
            P = dict(S.P); P.update(w32=0, w132=0, w212=0, w312=0, w_hs=0); P[key] = 10
            s1, _, _ = S.signals(P)
            sc1, _ = S.location(s1)
            t = S.run(s1, sc1 >= S.P["min_loc"], P=P)
            m = SC.metrics(t)
            cells.append(f"{name:<5} {m['R']:+.3f}/{m['n']}/{m['pf']:.2f}")
        P = dict(S.P); P["w_hs"] = 0
        s1, _, _ = S.signals(P); sc1, _ = S.location(s1)
        m = SC.metrics(S.run(s1, sc1 >= S.P["min_loc"], P=P))
        cells.append(f"no-hammer {m['R']:+.3f}/{m['n']}")
        print(f"  {mk:<6} " + "   ".join(cells))
    print("\nEntry buffer 0 / 20 / 50 / 100 pts (SL buffer moves with it):")
    for mk, (S, sig, ok, score, flags, t_all) in keep.items():
        cells = []
        for bf in (0.0, 20.0, 50.0, 100.0):
            P = dict(S.P); P["entry_buf"] = bf; P["sl_buf"] = bf
            m = SC.metrics(S.run(sig, ok, P=P))
            cells.append(f"{bf:>3.0f}: {m['R']:+.3f}/{m['n']}/{m['pf']:.2f}")
        print(f"  {mk:<6} " + "   ".join(cells))
    print("\nCost stress 0x / 1x / 1.5x / 2x:")
    for mk, (S, sig, ok, score, flags, t_all) in keep.items():
        cells = []
        for cm in (0.0, 1.0, 1.5, 2.0):
            m = SC.metrics(S.run(sig, ok, cost_mult=cm))
            cells.append(f"{cm:g}x {m['R']:+.3f}")
        print(f"  {mk:<6} " + "   ".join(cells))
    print("\nTimeframe, as configured (60m on all; 5m on NQ where 1-minute data exists):")
    for mk in SC.MARKETS:
        cells = []
        for tf in (("5min",) if mk == "NQ" else ()) + ("60min",):
            S = SC.Strat(mk, tf)
            sig, _, _ = S.signals(); sc, _ = S.location(sig)
            t = S.run(sig, sc >= S.P["min_loc"])
            m = SC.metrics(t)
            ctl, cnt_c, _ = SC.control(S, sig, sc >= S.P["min_loc"], np.ones(S.F["n"], np.int64),
                                       n_draws=200)
            cells.append(f"{tf}: {m['R']:+.3f}/{m['n']}/PF {m['pf']:.2f}/win {m['win']:.0%},"
                         f" control "
                         f"{np.mean(ctl):+.3f} p {np.mean(ctl >= m['R']):.2f}")
        print(f"  {mk:<6} " + "   ".join(cells))


if __name__ == "__main__":
    main()
