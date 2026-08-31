"""An INDEPENDENT re-implementation of the as-traded configuration, in vectorbt.

Why this exists: the verdict on this family rests on one engine, and on this branch vectorbt has
failed transcription three times (`STUDY_V53_UNDERFIT.md`). So it is used the way a second
opinion should be used -- re-derive the entry, stop and target signals from the bars with no
shared code path, hand them to `vbt.Portfolio.from_signals`, and compare the TRADE COUNT and the
per-trade points against `v58ib`. A disagreement is a finding either way.

The configuration is candidate C: 60-minute Initial Balance, 25% retracement entry, 60% stop,
50% target, both sides, flat 15:55, no filters -- what the user's indicator ships with.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402
from research.v38.v38feeds import load                                  # noqa: E402

RETR, STOPF, TGT, IBLEN, FLAT = 0.25, 0.60, 0.50, 60, 15 * 60 + 55


def plan(f, side):
    """Entry / stop / target series built straight from the bars, sharing nothing with v58ib."""
    ix = f.index
    mod = ix.hour * 60 + ix.minute
    dkey = ix.normalize()
    inib = (mod >= V.IB_OPEN) & (mod < V.IB_OPEN + IBLEN) & (ix.dayofweek < 5)
    g = f[inib].groupby(dkey[inib])
    hi, lo = g["high"].max(), g["low"].min()
    H = dkey.map(hi).to_numpy(float)
    L = dkey.map(lo).to_numpy(float)
    rng = H - L
    win = (mod >= V.IB_OPEN + IBLEN) & (mod < FLAT) & (ix.dayofweek < 5) & np.isfinite(rng) & (rng > 0)

    h, l, c = (f[k].to_numpy(float) for k in ("high", "low", "close"))
    if side == "long":
        ent, stp, tgt = H - rng * RETR, H - rng * STOPF, H + rng * TGT
        broke = win & (h > H)
    else:
        ent, stp, tgt = L + rng * RETR, L + rng * STOPF, L - rng * TGT
        broke = win & (l < L)

    # first break of the day, then the first later bar that touches the entry level
    day = dkey.to_numpy()
    entries = np.zeros(len(f), bool)
    i = 0
    n = len(f)
    while i < n:
        j = i
        while j < n and day[j] == day[i]:
            j += 1
        b = np.flatnonzero(broke[i:j])
        if len(b):
            k0 = i + b[0]
            for k in range(k0 + 1, j):
                if not win[k]:
                    break
                if (side == "long" and l[k] <= ent[k]) or (side != "long" and h[k] >= ent[k]):
                    entries[k] = True
                    break
        i = j
    return entries, ent, stp, tgt, win


def run(name):
    f = load(name)
    out = {}
    for side in ("long", "short"):
        entries, ent, stp, tgt, win = plan(f, side)
        px = pd.Series(np.where(entries, ent, f["close"].to_numpy(float)), index=f.index)
        sl = pd.Series(np.abs(ent - stp) / np.maximum(ent, 1e-9), index=f.index)
        tp = pd.Series(np.abs(tgt - ent) / np.maximum(ent, 1e-9), index=f.index)
        exits = pd.Series(~win & np.roll(win, 1), index=f.index)     # the session flatten
        pf = vbt.Portfolio.from_signals(
            close=pd.Series(f["close"].to_numpy(float), index=f.index),
            entries=pd.Series(entries, index=f.index) if side == "long" else False,
            short_entries=pd.Series(entries, index=f.index) if side == "short" else False,
            exits=exits if side == "long" else False,
            short_exits=exits if side == "short" else False,
            price=px, sl_stop=sl, tp_stop=tp, high=f["high"], low=f["low"],
            accumulate=False, freq="15min")
        t = pf.trades.records_readable
        pts = (t["Avg Exit Price"] - t["Avg Entry Price"]) * (1 if side == "long" else -1)
        out[side] = dict(n=len(t), pts=float(pts.mean()) if len(t) else np.nan,
                         win=float((pts > 0).mean()) if len(t) else np.nan)
    return out


def main():
    print("=" * 88)
    print("VECTORBT SECOND OPINION -- candidate C, the as-traded configuration, GROSS of costs")
    print("=" * 88)
    gi = None
    for mk in ("US30L", "US100L"):
        v = run(mk)
        # the same configuration through the study's own engine, gross
        F = V.build(mk)
        R, _ = V.outcomes(F, 0.0, fillbar=1)
        risk, atr = V.risk_atr(F)
        D = F["D"]
        li = int(np.flatnonzero(V.IB_LEN == IBLEN)[0])
        ri = int(np.flatnonzero(V.RETR == RETR)[0])
        si = int(np.flatnonzero(V.STOPF == STOPF)[0])
        ti = int(np.flatnonzero(V.TGT == TGT)[0])
        fi = int(np.flatnonzero(V.FLAT == FLAT)[0])
        gs = li * 450 + ri * 90 + si * 18 + ti * 3 + fi
        R3 = R.reshape(D, len(V.IB_LEN), 2, 450)
        for s, sd in (("long", 0), ("short", 1)):
            Rs = np.ascontiguousarray(R3[:, :, sd, :].reshape(D, V.NG))
            p = (Rs * risk)[:, gs]
            p = p[np.isfinite(p)]
            e = dict(n=len(p), pts=float(p.mean()), win=float((p > 0).mean()))
            b = v[s]
            print(f"  {mk:<7} {s:<6}  v58ib  n {e['n']:>5d}  {e['pts']:>+8.2f} pts  "
                  f"win {e['win']*100:>5.1f}%   |   vectorbt  n {b['n']:>5d}  "
                  f"{b['pts']:>+8.2f} pts  win {b['win']*100:>5.1f}%   "
                  f"| trade count {100*min(e['n'],b['n'])/max(e['n'],b['n'],1):.1f}% agreed")


if __name__ == "__main__":
    main()
