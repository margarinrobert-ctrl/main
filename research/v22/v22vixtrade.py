"""What the VIX is worth on REAL TRADES: heat, edge, and stop placement.

Part A established the split verdict that shapes this file. The VIX forecasts the MAGNITUDE of the
next move with an information coefficient of +0.58 on research rising to +0.78 on the locked block
-- an enormous, stable relationship. It forecasts the STRAIGHTNESS of that move not at all: the
research-to-locked IC correlation on the chop label is -0.638, a near-total sign inversion.

So the regime question ("is it about to chop or distribute") is answered NO, and the sizing question
("where does the stop go") is answered by the one thing the VIX is genuinely good at. That is the
whole design of this file: no chop filter is built, and the stop policy is built off the forward
volatility estimate instead.

THE MECHANISM BEING TESTED. An ATR stop is sized from TRAILING volatility. Volatility mean-reverts,
so trailing ATR is systematically too small when vol is low in its own distribution and too large
when it is high. The VIX is a FORWARD estimate of the same quantity. Where the two disagree --
implied above realised -- the ATR is the one that is wrong, and the stop should be widened.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v22")
import v22vix as X            # noqa: E402

NDRAW = 400
RUNGS = (10, 20, 30, 40, 50, 60, 70, 80, 90)


def controls(O, pool, k, ndraw=NDRAW, seed=0):
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    out = np.empty(ndraw)
    for dd in range(ndraw):
        # The control is drawn from the SAME overlapping signal pool the conditions are scored on,
        # so the overlap biases both identically and the EXCESS is still readable.
        idx = rng.choice(pool, size=k, replace=False)
        out[dd] = float(np.nanmean(O["R"][idx]))
    return out


if __name__ == "__main__":
    d = X.load()
    F = X.features(d)
    sig, atr, ex_lo = X.donchian(d)
    O = X.walk(d, sig, atr, ex_lo, stop_mult=2.0)
    res_d, lk_d = X.blocks(len(d))
    res, lk = res_d[sig], lk_d[sig]
    Fs = {k: v[sig] for k, v in F.items()}
    ok = np.isfinite(O["R"])

    base_r = X.lock(O, res & ok)
    base_l = X.lock(O, lk & ok)
    X.hdr("SPX DAILY DONCHIAN 30/20 LONG, 2.0N ATR STOP, NO TARGET -- the unfiltered baseline")
    print(f"   {len(sig)} raw breakout days.  2 bp round turn = "
          f"{np.nanmedian(d.c.to_numpy()[sig] * 2e-4 / (2.0 * atr[sig])):.2%} of the stop"
          f"  -- negligible at daily scale, which is why the daily result is a CLEAN read on")
    print( "   geometry rather than on execution.\n")
    print(f"   {'block':<12}{'signals':>9}{'locked n':>10}{'R/trade':>11}{'PF':>9}{'win':>8}"
          f"{'med hold':>10}")
    for lab, m, idx in (("research", res & ok, base_r), ("locked", lk & ok, base_l)):
        r = O["R"][m]
        print(f"   {lab:<12}{int(m.sum()):>9}{len(idx):>10}{np.nanmean(r):>+11.4f}"
              f"{X.pf(r):>9.3f}{(r>0).mean():>8.1%}"
              f"{np.median(O['xb'][m]-O['sig'][m]):>10.0f}")
    print()
    print( "   *** POWER NOTE, AND IT GOVERNS EVERY TABLE BELOW. ***  A daily trend trade holds a")
    print(f"   median of {int(np.median(O['xb'][res&ok]-O['sig'][res&ok]))} sessions, so the position lock leaves"
          f" only {len(base_r)} research and {len(base_l)} locked trades out of")
    print(f"   {int((res&ok).sum())} and {int((lk&ok).sum())} signals. n={len(base_l)} cannot support any verdict, and none is")
    print( "   offered: the tables below score the OVERLAPPING signal population, which measures the")
    print( "   right conditional means but has an effective sample far smaller than its n. The VIX")
    print( "   result this study rests on is the INFORMATION COEFFICIENT in part A, which uses every")
    print( "   session and does not depend on a backtest at all.")

    X.hdr("D. HEAT BY VIX REGIME -- MAE and MFE in ATR units. Is an ATR stop already VIX-adaptive?")
    print("   The ATR has already scaled for volatility in POINTS. The only question is whether it")
    print("   scaled ENOUGH. A flat column means yes and the VIX adds nothing to stop placement.\n")
    for feat in ("vrp_ratio20", "vix_pct250", "vix"):
        x = Fs[feat]
        g = np.isfinite(x) & ok
        for blk, tag in ((res, "research"), (lk, "locked")):
            gg = g & blk
            q = np.quantile(x[g & res], np.linspace(0, 1, 6))
            q[0] -= 1e-9
            q[-1] += 1e9
            dec = np.digitize(x, q) - 1
            print(f"   {feat:<14}{tag}")
            print(f"      {'quintile':>9}{'n':>6}{'MAE p50':>10}{'MAE p90':>10}{'MFE p50':>10}"
                  f"{'MFE p90':>10}{'R/trade':>10}{'stop-out':>10}")
            for j in range(5):
                m = gg & (dec == j)
                if m.sum() < 10:
                    continue
                # NO POSITION LOCK HERE. An excursion is a property of the SIGNAL, not of the
                # book, and the lock throws away 90% of a daily sample. R/trade in this table is
                # therefore OVERLAPPING and its n is signals, not independent trades.
                r = O["R"][m]
                print(f"      {j+1:>9}{int(m.sum()):>6}{np.nanquantile(O['mae'][m],.5):>10.2f}"
                      f"{np.nanquantile(O['mae'][m],.9):>10.2f}"
                      f"{np.nanquantile(O['mfe'][m],.5):>10.2f}"
                      f"{np.nanquantile(O['mfe'][m],.9):>10.2f}"
                      f"{np.nanmean(r):>+10.4f}"
                      f"{(O['why'][m]==0).mean():>10.1%}")
            print()

    X.hdr("E. THE STOP POLICY. Widen the stop where IMPLIED sits above REALISED -- and its INVERSE")
    print("   state = vrp_ratio20 = VIX / (20-day realised vol, annualised). Above 1 the option")
    print("   market expects more than the tape has delivered, so the trailing ATR is too small.")
    print("   The inverse policy is the sign check: if it also improves, the state is not the cause.\n")
    s = Fs["vrp_ratio20"]
    good = np.isfinite(s)
    thr = float(np.nanmedian(s[good & res]))
    hi = np.where(good, s > thr, False)
    print(f"   research median of vrp_ratio20 = {thr:.3f}\n")
    print(f"   {'policy':<34}{'RESEARCH':>28}{'|':>4}{'LOCKED':>28}")
    print(f"   {'':<34}{'n':>6}{'R/trade':>11}{'PF':>9}{'|':>4}{'n':>6}{'R/trade':>11}{'PF':>9}")
    print( "   n is OVERLAPPING SIGNALS, not independent trades -- see the power note above.")
    for lab, a, b in (("flat 2.0N", 2.0, 2.0),
                      ("wide when IMPLIED>REALISED 2.5/2.0", 2.5, 2.0),
                      ("wide when IMPLIED>REALISED 3.0/2.0", 3.0, 2.0),
                      ("wide when IMPLIED>REALISED 3.0/1.5", 3.0, 1.5),
                      ("INVERSE (naive)            2.0/3.0", 2.0, 3.0)):
        A = X.walk(d, sig, atr, ex_lo, stop_mult=a)
        B = X.walk(d, sig, atr, ex_lo, stop_mult=b)
        M = dict(sig=sig, xb=np.where(hi, A["xb"], B["xb"]),
                 R=np.where(hi, A["R"], B["R"]), why=np.where(hi, A["why"], B["why"]))
        line = f"   {lab:<34}"
        for blk in (res, lk):
            m = blk & good & np.isfinite(M["R"])
            r = M["R"][m]
            line += f"{int(m.sum()):>6}{r.mean():>+11.4f}{X.pf(r):>9.3f}"
            if blk is res:
                line += f"{'|':>4}"
        print(line)

    # ------------------------------------------------------------------ F. edge, control-gated
    rows = []
    pool_r = np.flatnonzero(res & ok)
    bank = {rg: controls(O, pool_r, max(8, int(round(len(pool_r) * rg / 100))), seed=900 + rg)
            for rg in RUNGS}
    for name, x in Fs.items():
        g = np.isfinite(x)
        if g.mean() < 0.85:
            continue
        for rg, t in zip(RUNGS, np.quantile(x[g & res], np.array(RUNGS) / 100.0)):
            for sgn, sl in ((+1, ">="), (-1, "<=")):
                m = (x >= t) if sgn > 0 else (x <= t)
                sel = 100 - rg if sgn > 0 else rg
                mr = m & g & res & ok
                if mr.sum() < 25:
                    continue
                ir = np.flatnonzero(mr)
                if len(ir) < 20:
                    continue
                rr = float(O["R"][ir].mean())
                b = bank[min(RUNGS, key=lambda z: abs(z - sel))]
                b = b[np.isfinite(b)]
                il = np.flatnonzero(m & g & lk & ok)
                rows.append(dict(feat=name, family=None, dirn=sl, rung=rg, n=len(ir), R=rr,
                                 ctrl=float(b.mean()), exc=rr - float(b.mean()),
                                 p=float((b >= rr).mean()), n_lk=len(il),
                                 R_lk=float(O["R"][il].mean()) if len(il) >= 12 else np.nan))
    df = pd.DataFrame(rows)
    df["exc_lk"] = df.R_lk - float(np.nanmean(O["R"][lk & ok]))
    df.to_csv("results/v22/v22_vix_trade.csv", index=False)

    X.hdr("F. EDGE BY VIX CONDITION, against a SELECTIVITY-MATCHED CONTROL -- top 50 by excess")
    print(f"   {len(df)} scorable conditions. At alpha 0.05, {0.05*len(df):.0f} pass by chance;"
          f" observed {int((df.p<=0.05).sum())}.")
    print(f"   Share of the WHOLE population beating its own control: {float((df.exc>0).mean()):.1%}"
          f"  (read this before the top row).\n")
    top = df.sort_values("exc", ascending=False).head(50)
    print(f"   {'#':>3} {'feature':<16}{'dir':>4}{'rung':>6}{'n':>6}{'R/trade':>10}{'ctrl':>9}"
          f"{'excess':>9}{'p':>7}{'|':>3}{'n':>5}{'LOCKED R':>10}{'vs base':>9}")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"   {i:>3} {r.feat:<16}{r.dirn:>4}{r.rung:>6}{int(r.n):>6}{r.R:>+10.4f}"
              f"{r.ctrl:>+9.4f}{r.exc:>+9.4f}{r.p:>7.3f}{'|':>3}{int(r.n_lk):>5}"
              f"{r.R_lk:>+10.4f}{r.exc_lk:>+9.4f}")
    print(f"\n   Of these 50, {int((top.exc_lk>0).sum())} beat the unfiltered baseline out of"
          f" sample. Chance is 50%.")
    v = df.dropna(subset=["exc_lk"])
    print(f"   Research excess vs locked excess, correlation over all {len(v)} conditions:"
          f" {np.corrcoef(v.exc, v.exc_lk)[0,1]:+.3f}")
