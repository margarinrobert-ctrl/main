"""B2 -- the audits, then the research block. The holdout is NOT touched here.

Order is deliberate: nothing about performance is read until causality, execution alignment and the
cost arithmetic have been checked, because any one of them can invalidate everything after it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breaker import bbcore as B  # noqa: E402

pd.set_option("display.width", 210)
BAR = "=" * 104
WHY = {0: "stop", 1: "target", 2: "cap"}


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    f = B.load()
    a = B.atr(f)
    cut = B.split_date(f)
    L = B.detect(f, a, B.EXPIRY, +1)
    S = B.detect(f, a, B.EXPIRY, -1)
    D = pd.concat([L, S]).sort_values("trig").reset_index(drop=True)
    print(f"  bars {len(f):,}   {f.index[0]} -> {f.index[-1]}")
    print(f"  HOLDOUT SPLIT (last 25% of trading days): {cut}   -- not read in this script")
    print(f"  setups detected: {len(D):,}  ({len(L):,} long / {len(S):,} short)")

    # ------------------------------------------------------------------ B2.0 causality
    hdr("B2.0  TRUNCATION AUDIT -- recompute on history that ENDS at bar X and require a match")
    print("  Every step is backward-looking by construction; this checks it rather than asserting.\n")
    ok_atr = ok_det = 0
    tot = 0
    for X in (200_000, 500_000, 800_000):
        a_tr = B.atr(f.iloc[:X])
        m = np.max(np.abs(a_tr - a[:X]))
        Lt = B.detect(f.iloc[:X], a_tr, B.EXPIRY, +1)
        St = B.detect(f.iloc[:X], a_tr, B.EXPIRY, -1)
        Dt = pd.concat([Lt, St]).sort_values("trig").reset_index(drop=True)
        lim = X - 4 * B.EXPIRY
        full = D[D.trig < lim].reset_index(drop=True)
        trun = Dt[Dt.trig < lim].reset_index(drop=True)
        cols = ["ob", "imp", "sweep", "viol", "trig", "zlo", "zhi", "side"]
        same = len(full) == len(trun) and bool((full[cols].to_numpy() == trun[cols].to_numpy()).all())
        ok_atr += int(m < 1e-12)
        ok_det += int(same)
        tot += 1
        print(f"  ends at bar {X:>8,}   max |ATR diff| {m:.3e}   setups full {len(full):>6,} vs "
              f"truncated {len(trun):>6,}   identical {same}")
    print(f"\n  AUDIT: {ok_atr}/{tot} ATR clean, {ok_det}/{tot} detection clean")

    # ------------------------------------------------------------------ B2.1 execution alignment
    hdr("B2.1  EXECUTION ALIGNMENT -- positions against returns, and the same-bar counterfactual")
    o = f["open"].to_numpy(); c = f["close"].to_numpy()
    ret = np.zeros(len(c)); ret[1:] = np.diff(c) / c[:-1]
    tA = B.walk(f, a, D, 2.0)
    pos = np.zeros(len(c))
    for s, e, sd in zip(tA.e_bar.to_numpy(), tA.x_bar.to_numpy(), tA.side.to_numpy()):
        pos[s:e + 1] = sd
    print(f"  bars in a position          {100*np.mean(pos != 0):.2f}%")
    print(f"  corr(position_t, return_t)      {np.corrcoef(pos, ret)[0,1]:+.5f}   "
          f"<- what the strategy EARNS, not a leak by itself")
    print(f"  corr(position_t, return_t+1)    "
          f"{np.corrcoef(pos[:-1], ret[1:])[0,1]:+.5f}")
    print(f"  corr(side, own trigger-bar return) "
          f"{np.corrcoef(tA.side, (c[tA.trig] - o[tA.trig]) / o[tA.trig])[0,1]:+.5f}   "
          f"<- negative is EXPECTED: a long triggers when price dips into the zone")
    print("\n  The decisive test is the counterfactual: fill at the trigger bar's CLOSE instead of")
    print("  the next bar's OPEN. If that manufactures performance, next-bar execution is load-bearing.")
    tSame = B.walk(f.assign(open=f["close"]), a, D.assign(trig=D.trig - 1), 2.0)
    for lab, t in (("next-bar open (as run)", tA), ("SAME-BAR close (leak)", tSame)):
        s = B.stats(t)
        sh, _ = B.daily_sharpe(t, f)
        print(f"    {lab:<24} n {s['n']:>6}  win {s['win']:.4f}  PF {s['pf']:.3f}  "
              f"{s['mean']:+.5f} %/trade  ann Sharpe {sh:+.3f}")
    print("\n  Also: push every fill one MORE bar later. An edge that lives entirely in one minute")
    print("  is an execution artifact, not a signal.")
    for k in (1, 2, 5):
        t = B.walk(f, a, D.assign(trig=D.trig + k), 2.0)
        s = B.stats(t)
        print(f"    fill at open[trig+{1+k}]      n {s['n']:>6}  win {s['win']:.4f}  "
              f"PF {s['pf']:.3f}  {s['mean']:+.5f} %/trade")

    # ------------------------------------------------------------------ B2.2 costs
    hdr("B2.2  COST -- gross beside net from the first run, and the breakeven in bps")
    print(f"  {'primary':<14}{'n':>7}{'cost/risk':>11}{'gross PF':>10}{'net PF':>9}"
          f"{'gross %/tr':>12}{'net %/tr':>11}{'BE cost (bps)':>15}")
    for lab, rr in (("A  2R", 2.0), ("B  no target", 0.0)):
        t = B.walk(f, a, D, rr)
        g = B.stats(t, "gross_pct"); nn = B.stats(t, "pct")
        be_pts = t.gross_pts.mean()
        be_bps = 1e4 * be_pts / t.ent.mean()
        print(f"  {lab:<14}{nn['n']:>7}{t.cost_frac.median():>11.3f}{g['pf']:>10.3f}"
              f"{nn['pf']:>9.3f}{g['mean']:>+12.5f}{nn['mean']:>+11.5f}{be_bps:>15.3f}")
    print("\n  BE cost (bps) = the round turn, in basis points of entry price, at which the GROSS")
    print("  edge is exactly consumed. Charged cost is "
          f"{1e4*B.RT_POINTS/float(tA.ent.mean()):.3f} bps.")
    print(f"\n  {'primary':<14}{'0x':>11}{'1x (real)':>12}{'2x':>11}{'4x':>11}")
    for lab, rr in (("A  2R", 2.0), ("B  no target", 0.0)):
        row = []
        for mlt in (0.0, 1.0, 2.0, 4.0):
            t = B.walk(f, a, D, rr, cost=B.RT_POINTS * mlt)
            row.append(B.stats(t)["mean"])
        print(f"  {lab:<14}" + "".join(f"{v:>+11.5f}  " if i else f"{v:>+11.5f}  "
                                       for i, v in enumerate(row)))

    # ------------------------------------------------------------------ B2.3 the research block
    hdr("B2.3  RESEARCH BLOCK ONLY (before 2025-03-17) -- both primaries, both sides")
    print(f"  {'primary':<14}{'block':<10}{'n':>7}{'win':>8}{'BE win':>8}{'PF':>8}"
          f"{'%/trade':>10}{'total%':>10}{'annSharpe':>11}{'maxDD%':>9}{'amb':>7}")
    for lab, rr in (("A  2R", 2.0), ("B  no target", 0.0)):
        t = B.walk(f, a, D, rr)
        r = t[pd.DatetimeIndex(t.ts) < cut]
        cf = float(r.cost_frac.median())
        be = (1.0 + cf) / (1.0 + 2.0) if rr > 0 else np.nan
        s = B.stats(r)
        sh, _ = B.daily_sharpe(r, f[f.index < cut])
        print(f"  {lab:<14}{'research':<10}{s['n']:>7}{s['win']:>8.4f}"
              f"{be:>8.4f}{s['pf']:>8.3f}{s['mean']:>+10.5f}{s['total']:>+10.2f}"
              f"{sh:>+11.3f}{s['dd']:>9.2f}{r.amb.mean():>7.4f}")
        for sd, nm in ((1, "  long"), (-1, "  short")):
            ss = B.stats(r[r.side == sd])
            print(f"  {nm:<14}{'':<10}{ss['n']:>7}{ss['win']:>8.4f}{'':>8}{ss['pf']:>8.3f}"
                  f"{ss['mean']:>+10.5f}{ss['total']:>+10.2f}")
        mix = r.why.map(WHY).value_counts(normalize=True)
        print(f"  {'':<14}exit mix: " + "  ".join(f"{k} {v:.3f}" for k, v in mix.items())
              + f"   median hold {r.hold.median():.0f} min")
        print()


if __name__ == "__main__":
    main()
