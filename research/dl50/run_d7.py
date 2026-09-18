"""The 150/50-point arm re-expressed in ATR, and ADX <= 20 tested on it.

THE ARM BEING WORKED ON. 07:00-11:00 New York ENTRIES, no flatten, Donchian 20 + EMA200 state,
fixed 50-point stop and 150-point target: research +1.513 pts at PF 1.041 and holdout -1.722 at
0.956. It is the best research cell in the study and it inverts out of sample.

THE HYPOTHESIS BEING TESTED. That inversion may not be a decayed edge at all. A fixed 50-point stop
is 4.23 ATR in 2016 and 1.10 ATR in 2025, so the research block is a wide-stop swing system and the
holdout is a tight scalp -- two different strategies wearing one spec. Sizing the stop as k x ATR
at the SIGNAL bar and the target as 3 x that stop keeps the reward:risk at 3 and makes the geometry
constant. If the inversion is a geometry artifact it should shrink; if it is decay it should not.

Both nulls are run. The ENTRY null asks whether the trigger beats a random bar with the same
management; the FILTER null asks whether ADX <= 20 beats a random gate keeping the same share.
Scored in POINTS and in R -- R is safe here because the stop is k x ATR, never a structural level.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402

RNG = np.random.default_rng(15050)
ND = 400
M0, M1, HOLD, TGT_R = 420, 660, 96, 3.0
STOPS = (1.0, 1.25, 1.5, 2.0)


def main():
    f = D.load(15)
    sess = np.unique(f.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy()
    mod = f["mod"].to_numpy().astype(np.int64)
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    a14, _, _ = D.adx(f, 14)
    ones = np.ones(len(c), np.int64)
    gate_lo = (a14 <= 20).astype(np.int64)
    gate_hi = (a14 >= 25).astype(np.int64)

    print("GEOMETRY: the point barrier against the ATR barrier, stop in ATR by year")
    g = D.geometry(f)
    print(f"  50 points   2016 {g['in_atr'].iloc[0]:.2f} ATR -> 2025 {g['in_atr'].iloc[-1]:.2f} ATR"
          f"   ({g['in_atr'].iloc[0]/g['in_atr'].iloc[-1]:.2f}x drift)")
    print("  k x ATR     constant at k by construction, every year   (1.00x drift)")

    print(f"\n07:00-11:00 ENTRIES, no flatten, R = {TGT_R:.0f}. Break-even win rate "
          f"{100/(1+TGT_R):.2f}% driftless, plus cost.")
    print(f"{'barrier':<18}{'blk':<10}{'n':>6}{'win%':>8}{'pts':>9}{'R':>9}{'PF':>7}"
          f"{'hold':>7}{'cost/risk':>10}{'ctl R':>9}{'p':>7}")
    rows = {}
    for nm, kind, k in [("50 / 150 points", "pts", None)] + [(f"{s} ATR / {TGT_R:.0f}R", "atr", s)
                                                             for s in STOPS]:
        if kind == "pts":
            eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, 150.0,
                                             HOLD, D.COST, M0, M1, mod, -1)
            rr = r / D.STOP_PTS
            cr = np.full(len(r), D.COST / D.STOP_PTS)
        else:
            eb, r, rr, sd, hl, why, amb = D.walk_atr(o, h, l, c, at, eh, el, ou, od, k, TGT_R,
                                                     HOLD, D.COST, M0, M1, mod, -1, ones)
            cr = D.COST / (k * at[eb - 1])
        ts = f.index[eb]
        sig = eb - 1
        rows[nm] = (sig, sd, r, rr, ts, k, kind)
        for bl, sel in (("research", np.asarray(ts < cut)), ("HOLDOUT", np.asarray(ts >= cut))):
            if sel.sum() < 30:
                continue
            # matched random ENTRY with the identical management
            elig = np.flatnonzero(np.isfinite(at) & (at > 0) & (mod >= M0) & (mod < M1))
            blk = np.flatnonzero(f.index < cut) if bl == "research" else np.flatnonzero(f.index >= cut)
            e2 = elig[np.isin(elig, blk)]
            e2 = e2[(e2 > 300) & (e2 < len(c) - 100)]
            share = float((sd[sel] > 0).mean())
            ctl = np.empty(ND)
            for i in range(ND):
                pick = np.sort(RNG.choice(e2, size=min(int(sel.sum()), len(e2)), replace=False))
                sr = np.where(RNG.random(len(pick)) < share, 1, -1)
                if kind == "pts":
                    q = D.walk_at(o, h, l, c, pick.astype(np.int64), sr.astype(np.int64),
                                  D.STOP_PTS, 150.0, HOLD, D.COST, mod, -1)
                    ctl[i] = np.nanmean(q) / D.STOP_PTS
                else:
                    _, qr = D.walk_at_atr(o, h, l, c, at, pick.astype(np.int64),
                                          sr.astype(np.int64), k, TGT_R, HOLD, D.COST, mod, -1)
                    ctl[i] = np.nanmean(qr)
            mR = float(np.nanmean(rr[sel]))
            print(f"{nm:<18}{bl:<10}{int(sel.sum()):>6}{float((r[sel]>0).mean())*100:>7.2f}%"
                  f"{np.nanmean(r[sel]):>9.3f}{mR:>9.4f}{D.pf(r[sel]):>7.3f}"
                  f"{np.median(hl[sel])*15:>6.0f}m{np.nanmedian(cr[sel]):>10.3f}"
                  f"{np.nanmedian(ctl):>9.4f}{float(np.mean(ctl >= mR)):>7.3f}")
        print()

    print("ADX <= 20 AS A VETO on the ATR version, re-simulated vs a random gate of the same share")
    print(f"{'barrier':<18}{'gate':<14}{'blk':<10}{'n':>6}{'R':>9}{'PF':>7}{'kept':>7}"
          f"{'ctl R':>9}{'p':>7}")
    for k in STOPS:
        for gname, gm in (("(none)", ones), ("ADX <= 20", gate_lo), ("ADX >= 25", gate_hi)):
            eb, r, rr, sd, hl, why, amb = D.walk_atr(o, h, l, c, at, eh, el, ou, od, k, TGT_R,
                                                     HOLD, D.COST, M0, M1, mod, -1, gm)
            ts = f.index[eb]
            for bl, sel in (("research", np.asarray(ts < cut)), ("HOLDOUT", np.asarray(ts >= cut))):
                if sel.sum() < 30:
                    continue
                mR = float(np.nanmean(rr[sel]))
                p = np.nan; ctlm = np.nan; kept = 1.0
                if gname != "(none)":
                    # the base's signal bars in this block, gated at random to the same share
                    eb0, r0, rr0, sd0, _, _, _ = D.walk_atr(o, h, l, c, at, eh, el, ou, od, k,
                                                            TGT_R, HOLD, D.COST, M0, M1, mod,
                                                            -1, ones)
                    ts0 = f.index[eb0]
                    s0 = np.asarray(ts0 < cut) if bl == "research" else np.asarray(ts0 >= cut)
                    sb, db = (eb0 - 1)[s0], sd0[s0]
                    kept = float(gm[sb].mean())
                    kn = max(int(round(kept * len(sb))), 5)
                    ctl = np.empty(ND)
                    for i in range(ND):
                        pick = np.sort(RNG.choice(len(sb), size=kn, replace=False))
                        _, qr = D.walk_at_atr(o, h, l, c, at, sb[pick].astype(np.int64),
                                              db[pick].astype(np.int64), k, TGT_R, HOLD,
                                              D.COST, mod, -1)
                        ctl[i] = np.nanmean(qr)
                    ctlm = float(np.nanmedian(ctl)); p = float(np.mean(ctl >= mR))
                print(f"{f'{k} ATR':<18}{gname:<14}{bl:<10}{int(sel.sum()):>6}{mR:>9.4f}"
                      f"{D.pf(r[sel]):>7.3f}{kept:>7.2f}{ctlm:>9.4f}{p:>7.3f}")
        print()


if __name__ == "__main__":
    main()
