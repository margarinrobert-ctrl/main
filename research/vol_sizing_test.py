"""Which strategies actually need volatility sizing, and which of the eight methods delivers.

The diagnostic runs first: if per-trade dollar risk barely varies, no sizing method can change
anything and a flat result means "nothing to fix", not "the method failed".
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import vol_sizing as VS
from test_suite import build

STRATS = [
    ("RSI/wick 1R",      ["RSI14>70", "lower wick>50%"],                 1, 2.5, 1.0,   0, 60),
    ("vol/midday/EMA200",["vol rising", "midday", "dist EMA200>2 ATR"],  1, 2.5, 3.0,   0, 30),
    ("VWAP/Stoch/ADX",   ["close>session VWAP", "Stoch K>D", "ADX>20"],  1, 1.5, 3.0,   0, 30),
    ("EMA10/body/mom",   ["close>EMA10", "body>60%", "5-bar momentum>0"],1, 2.5, 3.0,   0, 30),
    ("RSI/Williams/ADX", ["RSI14<30", "Williams%R<-80", "ADX>25"],       1, 2.5, 3.0,   0, 30),
    ("MFI/first hour 1R",["MFI>80", "first hour"],                       1, 2.5, 1.0,   0, 60),
]

if __name__ == "__main__":
    print("STEP 1 -- does per-trade risk vary enough for sizing to matter at all?")
    print(f"  {'strategy':<22}{'trades':>8}{'risk CV':>10}{'min $':>9}{'max $':>9}{'verdict':>28}")
    built = []
    for nm, c, side, am, tp, fl, tf in STRATS:
        s = build(c, side=side, atr_mult=am, tp_r=tp, flat_min=fl, tf=tf)
        cv, risk = VS.dispersion(s, am)
        v = "sizing can help" if cv > 0.30 else ("marginal" if cv > 0.15 else "NOTHING TO FIX")
        print(f"  {nm:<22}{len(s.pnl):>8}{cv:>10.2f}{risk.min():>9,.0f}{risk.max():>9,.0f}{v:>28}")
        built.append((nm, s, am, cv))

    print("\nSTEP 2 -- the eight methods, on every strategy. $50,000 account, 1% risk, 10-lot cap.")
    print("  Ranked on MAR (net / max drawdown) because it is scale invariant; dollars are not.")
    wins = {m: 0 for m in VS.METHODS}
    for nm, s, am, cv in built:
        rows = [VS.evaluate(s, m, am) for m in VS.METHODS]
        base = rows[0]
        print(f"\n  {nm}   (risk CV {cv:.2f})")
        print(f"    {'method':<8}{'mean lots':>11}{'net $':>10}{'locked $':>10}{'maxDD $':>10}"
              f"{'Sharpe':>8}{'MAR':>7}{'vs fixed MAR':>14}")
        best, bm = -1e9, "fixed"
        for r in rows:
            d = r["mar"] - base["mar"]
            if r["lok"] > 0 and r["mar"] > best:
                best, bm = r["mar"], r["method"]
            print(f"    {r['method']:<8}{r['mean_lots']:>11.1f}{r['net']:>10,.0f}{r['lok']:>10,.0f}"
                  f"{r['dd']:>10,.0f}{r['sharpe']:>8.2f}{r['mar']:>7.2f}{d:>+14.2f}")
        wins[bm] += 1
        print(f"    best by MAR among those still profitable on the locked block: {bm}")

    print(f"\nSTEP 3 -- tally across {len(built)} strategies")
    for m, w in sorted(wins.items(), key=lambda x: -x[1]):
        if w:
            print(f"    {m:<8}best on {w} of {len(built)}")

    print("\nSTEP 4 -- AVA across the legs as a book")
    legs = [s for _, s, _, _ in built]
    ava_p, eq_p = VS.ava(legs)
    def sh(x):
        return float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if x.std() > 0 else 0.0
    def dd(x):
        e = np.cumsum(x); return float((np.maximum.accumulate(np.r_[0, e]) - np.r_[0, e]).max())
    print(f"    equal lots        net ${eq_p.sum():>9,.0f}  Sharpe {sh(eq_p):>5.2f}  "
          f"maxDD ${dd(eq_p):>8,.0f}  MAR {eq_p.sum()/max(dd(eq_p),1):>5.2f}")
    print(f"    AVA (1/sigma)     net ${ava_p.sum():>9,.0f}  Sharpe {sh(ava_p):>5.2f}  "
          f"maxDD ${dd(ava_p):>8,.0f}  MAR {ava_p.sum()/max(dd(ava_p),1):>5.2f}")
