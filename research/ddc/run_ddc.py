"""The Double Donchian backtest on US30, US100 and NQ, hourly, exactly as configured, then the
things the Strategy Tester will not tell you: literal vs intended take-profit, per year, per
side, the January-2024 window the header names, a random-entry control with identical exits,
the volatility filter's pass rate on an index, and a small ladder on the two parameters that
were fitted to BTC."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from ddc import ddc_core as D  # noqa: E402

OUT = "results/ddc"
os.makedirs(OUT, exist_ok=True)


def row(label, eq, t):
    m = D.metrics(eq, t)
    return (f"  {label:<34} n {m['n']:>4}  net {m['net']:+8.1%}  PF {m['pf']:5.2f}"
            f"  win {m['win']:5.1%}  maxDD {m['dd']:6.1%}  move/trade {m['ret']:+.3%}"
            f"  median hold {m['hold']:.0f}h")


def main():
    print("=" * 100)
    print("DOUBLE DONCHIAN CHANNEL BREAKOUT (50 / 30, width > 3%, TP 2% on 50%, 100% equity,")
    print("0.05%/side, no stop) -- 1-hour bars, US30 / US100 / NQ, whole file, as configured")
    print("=" * 100)
    for mk in D.MARKETS:
        b = D.bars(mk)
        S = D.signals(b)
        yrs = b.index.year
        print(f"\n{mk}: {len(b):,} hourly bars {b.index[0]:%Y-%m-%d} to {b.index[-1]:%Y-%m-%d}; "
              f"buy-and-hold {b.close.iloc[-1] / b.close.iloc[0] - 1:+.1%}")
        fark = S["fark"]
        ok = np.isfinite(fark)
        print(f"  width filter (slow channel > 3% of its low): passes on "
              f"{np.mean(fark[ok] > 3):.1%} of bars; raw breakouts up "
              f"{int(S['raw_up'].sum())} / down {int(S['raw_dn'].sum())}, "
              f"after the filter {int(S['long'].sum())} / {int(S['short'].sum())}")
        eqL, tL = D.run(b, S, literal=True)
        eqI, tI = D.run(b, S, literal=False)
        print(row("LITERAL (TP re-issued every bar)", eqL, tL))
        print(row("INTENDED (one partial per trade)", eqI, tI))
        # how far the literal halving goes
        print(row("  literal, long only", *D.run(b, S, literal=True, use_short=False)))
        print(row("  literal, short only", *D.run(b, S, literal=True, use_long=False)))
        print(row("  literal, zero commission", *D.run(b, S, literal=True, comm=0.0)))
        print(row("  literal, 0.10%/side", *D.run(b, S, literal=True, comm=0.001)))
        # per year, literal
        t = tL.copy()
        t["year"] = yrs[t.ent]
        eqy = eqL.groupby(yrs).agg(["first", "last"])
        eqy["ret"] = eqy["last"] / eqy["first"] - 1
        g = t.groupby("year").agg(n=("pnl", "size"), win=("pnl", lambda x: (x > 0).mean()),
                                  move=("ret", "mean"))
        g["equity_ret"] = eqy["ret"].reindex(g.index)
        print("  per year (literal):")
        print("    " + g.to_string(float_format=lambda x: f"{x:+.3f}").replace("\n", "\n    "))
        # the header's window: January 2024
        jan = (b.index >= "2024-01-01") & (b.index < "2024-02-01")
        if jan.sum() > 100:
            bj = b[jan]
            Sj = D.signals(pd.concat([b[b.index < "2024-01-01"].tail(60), bj]))
            for k in ("long", "short", "exit_long", "exit_short"):
                Sj[k] = Sj[k][-len(bj):]
            print(row("  header window 2024-01 only", *D.run(bj, Sj, literal=True)))
        # exposure, from the trade list
        nb = len(b)
        lo = int(tL[tL.side > 0].hold_h.sum()); sh = int(tL[tL.side < 0].hold_h.sum())
        print(f"  time in market: long {lo / nb:.1%} of bars, short {sh / nb:.1%}; "
              f"buy-and-hold over the same file "
              f"{b.close.iloc[-1] / b.close.iloc[0] - 1:+.1%}")
        # controls, matched on trades taken
        obs = eqL.iloc[-1] / 1000.0 - 1.0
        for pool in ("filter", "any"):
            ctl, cnt = D.control(b, S, n_draws=300, pool=pool, literal=True)
            lab = ("random bar INSIDE the width regime" if pool == "filter"
                   else "random bar anywhere")
            print(f"  control, {lab:<36} (300 draws, {cnt:.0f} trades/draw vs {len(tL)}): median "
                  f"net {np.median(ctl):+.1%}, mean {np.mean(ctl):+.1%}; P(control >= strategy) "
                  f"{np.mean(ctl >= obs):.3f}")
        tL.to_csv(f"{OUT}/trades_{mk}_literal.csv", index=False)
        tI.to_csv(f"{OUT}/trades_{mk}_intended.csv", index=False)
    print("\nLADDER on the two BTC-fitted knobs, literal model, net % over the whole file:")
    print("  width filter %:  " + "  ".join(f"{v:>7}" for v in (0, 1, 2, 3, 4, 5)))
    for mk in D.MARKETS:
        b = D.bars(mk)
        vals = []
        for v in (0, 1, 2, 3, 4, 5):
            S = D.signals(b, vol=float(v))
            eq, t = D.run(b, S, literal=True)
            vals.append(f"{eq.iloc[-1] / 1000 - 1:+6.0%}/{len(t)}")
        print(f"  {mk:<6}           " + "  ".join(f"{v:>7}" for v in vals) + "   (net / trades)")
    print("  take-profit %:   " + "  ".join(f"{v:>7}" for v in (1, 2, 3, 5)) + "  (width 3%)")
    for mk in D.MARKETS:
        b = D.bars(mk)
        S = D.signals(b)
        vals = []
        for tp in (1, 2, 3, 5):
            eq, t = D.run(b, S, tp_pct=tp / 100.0, literal=True)
            vals.append(f"{eq.iloc[-1] / 1000 - 1:+6.0%}/{len(t)}")
        print(f"  {mk:<6}           " + "  ".join(f"{v:>7}" for v in vals))
    print("\nTIMEFRAME, as configured (literal), net / trades / PF:")
    for tf in ("15min", "60min", "240min"):
        line = f"  {tf:<7}"
        for mk in D.MARKETS:
            b = D.bars(mk, tf)
            S = D.signals(b)
            eq, t = D.run(b, S, literal=True)
            m = D.metrics(eq, t)
            line += f"  {mk} {m['net']:+7.1%} / {m['n']:>4} / {m['pf']:.2f}   "
        print(line)


if __name__ == "__main__":
    main()
