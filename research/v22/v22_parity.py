"""The shipped V22 script's order model, re-implemented in Python and diffed against the engine.

A Pine port cannot be asserted by reading it (STUDY_PINE_PARITY: a script that was transcribed line
by line, read back twice and shipped lint-clean did not compile, and three of its rules were wrong).
So this file re-derives EVERY series the way the Pine does -- `ta.percentrank` semantics, the entry
channel's [1] and the exit channel's absence of one, the signal-bar-close stop anchor, the exit
order placed WITH the entry, and the rule that a signal may not fire on the bar a trade closed --
and diffs the result against `v16core`.

Two runs, as the study protocol requires:
  1  SERIES PARITY -- does the Pine's construction of the volatility percentile reproduce the
     research feature exactly? This is the transcription check and must come back near-perfect.
  2  ORDER-MODEL PARITY -- trade for trade against the engine, on the same bars.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v22")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v22vol as V            # noqa: E402
from v22stop import STATE, blocks  # noqa: E402
import v22anchor as A         # noqa: E402


def pine_percentrank(x, n):
    """`ta.percentrank(src, n)`: percent of the PREVIOUS n values that are <= the current one."""
    s = pd.Series(x)
    return s.rolling(n + 1).apply(lambda w: float((w[:-1] <= w[-1]).mean()), raw=True).to_numpy()


def pine_series(o, h, l, c, entry_n=30, exit_n=20, atr_len=14, vol_len=20, rank_len=250):
    """Exactly what the script computes, in the order it computes it."""
    atr = I.ema(I.true_range(h, l, c), atr_len)
    lr = np.r_[np.nan, np.diff(np.log(c))]
    cc = np.sqrt(pd.Series(lr ** 2).rolling(vol_len).mean().to_numpy())
    vol_pct = pine_percentrank(cc, rank_len - 1)
    ent_hi = I.shift(pd.Series(h).rolling(entry_n).max().to_numpy(), 1)
    ex_lo = pd.Series(l).rolling(exit_n).min().to_numpy()   # NO offset -- see the script comment
    return atr, vol_pct, ent_hi, ex_lo


def pine_run(o, h, l, c, atr, vol_pct, ent_hi, ex_lo, thresh=0.5, calm=2.5, fast=1.5):
    """The script's order model. Bar-close evaluation, one position, exit live on the entry bar."""
    n = len(c)
    trades = []
    pos = False
    last_exit = -2
    anchor = np.nan
    entry_px = np.nan
    sig_bar = -1
    for j in range(1, n):
        if pos:
            ch = ex_lo[j - 1]
            lvl = min(max(anchor, ch) if np.isfinite(ch) else anchor, c[j - 1])
            if l[j] <= lvl:
                trades.append((sig_bar, j, lvl - entry_px, lvl))
                pos = False
                last_exit = j
                continue
        if not pos and (j - 1) > last_exit:
            i = j - 1
            ready = (np.isfinite(ent_hi[i]) and np.isfinite(atr[i]) and atr[i] > 0
                     and np.isfinite(vol_pct[i]))
            if ready and h[i] > ent_hi[i]:
                sm = calm if vol_pct[i] <= thresh else fast
                anchor = c[i] - sm * atr[i]
                entry_px = o[j]
                sig_bar = i
                pos = True
                # The exit is live on the ENTRY bar, so test it immediately. The level was
                # written at the close of the signal bar i = j-1, from that bar's channel value.
                ch = ex_lo[j - 1]
                lvl = min(max(anchor, ch) if np.isfinite(ch) else anchor, c[j - 1])
                if l[j] <= lvl:
                    trades.append((sig_bar, j, lvl - entry_px, lvl))
                    pos = False
                    last_exit = j
    return trades


if __name__ == "__main__":
    for tf in (15, 30):
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        o, h, l, c = P["o"], P["h"], P["l"], P["c"]
        atr, vol_pct, ent_hi, ex_lo = pine_series(o, h, l, c)

        print("\n" + "=" * 106)
        print(f"NQ {tf}m   RUN 1 -- SERIES PARITY. The Pine construction against the research feature.")
        print("=" * 106)
        rf = V.build(o, h, l, c)[STATE]
        g = np.isfinite(rf) & np.isfinite(vol_pct)
        print(f"   `ta.percentrank(ccVol, 249)` vs research `{STATE}`")
        print(f"      bars compared      {int(g.sum())}")
        print(f"      max |difference|   {np.max(np.abs(vol_pct[g] - rf[g])):.3e}")
        print(f"      correlation        {np.corrcoef(vol_pct[g], rf[g])[0,1]:.10f}")
        ea = np.isfinite(atr) & np.isfinite(P["atr"])
        print(f"   ATR: max |difference| {np.max(np.abs(atr[ea] - P['atr'][ea])):.3e}")
        eh = np.isfinite(ent_hi) & np.isfinite(P["ent_hi"])
        print(f"   entry channel: disagreements {int((ent_hi[eh] != P['ent_hi'][eh]).sum())}")
        # The script reads `ta.lowest(low, 20)` at the close of bar j-1 and the order it writes is
        # live during bar j, so the script's value at j-1 must equal the engine's ex_lo at j.
        a_, b_ = ex_lo[:-1], P["ex_lo"][1:]
        ex = np.isfinite(a_) & np.isfinite(b_)
        print(f"   exit channel (script[j-1] vs engine[j]): disagreements "
              f"{int((a_[ex] != b_[ex]).sum())} of {int(ex.sum())}")

        print("\n" + "=" * 106)
        print(f"NQ {tf}m   RUN 2 -- ORDER-MODEL PARITY. The script's trades against the engine's.")
        print("=" * 106)
        T = pine_run(o, h, l, c, atr, vol_pct, ent_hi, ex_lo)
        sig = C.signals(P, 1)
        s = V.build(o, h, l, c)[STATE][sig]
        good = np.isfinite(s)
        smult = np.where(np.where(good, s <= 0.5, False), 2.5, 1.5)
        E = A.run(P, sig, smult, 1)
        idx = C.take(E, good & (E["xb"] >= 0))
        eng = {int(E["sig"][k]): (int(E["xb"][k]), float(E["pnl"][k])) for k in idx}
        scr = {int(t[0]): (int(t[1]), float(t[2])) for t in T}
        shared = sorted(set(eng) & set(scr))
        print(f"   engine trades {len(eng)}   script trades {len(scr)}   SHARED SIGNAL BARS"
              f" {len(shared)}  ({len(shared)/max(1,len(eng)):.1%} of the engine's)")
        if shared:
            same = sum(1 for k in shared if eng[k][0] == scr[k][0])
            ep = np.array([eng[k][1] for k in shared])
            sp = np.array([scr[k][1] for k in shared])
            print(f"   SAME EXIT BAR      {same}/{len(shared)} = {same/len(shared):.2%}")
            print(f"   per-trade points correlation  {np.corrcoef(ep, sp)[0,1]:.6f}")
            print(f"   engine pts/trade {ep.mean():+.4f}   script pts/trade {sp.mean():+.4f}"
                  f"   (the script pays no fee here; the engine's is netted)")
        only_e = sorted(set(eng) - set(scr))
        only_s = sorted(set(scr) - set(eng))
        print(f"   signals the ENGINE took and the script did not: {len(only_e)}")
        print(f"   signals the SCRIPT took and the engine did not: {len(only_s)}")
