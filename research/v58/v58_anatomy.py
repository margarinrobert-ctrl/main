"""REVERSE-ENGINEERING THE INITIAL BALANCE MODEL: which condition actually creates the edge?

`STUDY_V58_INITIAL_BALANCE.md` rejected the IB retracement family on three markets and found ONE
survivor -- a cluster read once on NQ, an instrument that had no part in the search: 48 trades,
+0.3544 ATR/trade, PF 1.801, beating a risk-matched random entry at p 0.003. This module asks what
that number is MADE OF.

THE PROCEDURE IS `STUDY_M4_ANATOMY.md`'s, because that study found a strategy whose barriers earned
nothing and whose "edge" was a day filter wearing a barrier costume. The four tests that exposed it
are run here in the same order, and every one of them can kill the result:

  1. EXIT SPLIT. Where does the money actually come from -- the stop, or the 15:55 flatten? A rule
     earning at the TIME exit is a direction bet on the session, not a barrier edge.
  2. WIDEN THE STOP UNTIL THE BARRIERS STOP BINDING. If an INFINITE stop earns as much as the
     shipped 1.00, the stop is decoration. M4's infinite stop earned MORE than its 4xATR.
  3. DAY VERSUS BAR. On the SAME selected days, does a RANDOM entry with the same geometry do as
     well? That separates "these are good days" from "this is a good entry".
  4. WHAT DO THE SELECTED DAYS DO ON THEIR OWN? Open-to-close in ATR units against every other day.
     If the chosen sessions simply drift up, the conditions are a session picker.

Then the part the brief asks for directly:

  5. DROP-ONE AND ALONE. Each of the four conditions removed from the full rule, and each one run
     by itself, so a condition that contributes nothing is visible as a condition that changes
     nothing.
  6. THE LADDER. Every rung of every condition's own axis. A real mechanism decays smoothly across
     its neighbourhood; a threshold that works at exactly one setting is not a mechanism.

Scoring is in ATR UNITS AT THE PLAN BAR, never in R: the stop is a swept fraction and R would pay a
configuration for tightening its own denominator. Net of a $1.44 MNQ round turn. The fill bar
carries its own stop.

Usage: python3 research/v58/v58_anatomy.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from research.v58 import v58ib as V                       # noqa: E402
from research.v58.v58judge import control_p               # noqa: E402
from research.v58.v58lock import fidx, gidx, boot         # noqa: E402
from research.v58.v58_nq import load_nq, COST_NQ          # noqa: E402

# the cluster, exactly as it was declared before NQ was opened
CLUSTER = dict(ib=30, retr=0.50, stop=1.00, tgt=99.0, flat=955, side="long",
               adx="adx>=20", vol="ibr>=0.8x", cpos="cpos>=0.5", ema="13 under 48")
COND = ("adx", "vol", "cpos", "ema")
LADDER = dict(adx=V.ADX_MODE, vol=V.VOL_MODE, cpos=V.CPOS_MODE, ema=V.EMA_MODE)


def prep(stopf=None):
    """Build the day tensor. `stopf` replaces V.STOPF in place, SAME LENGTH so every geometry
    index still decodes -- that is how an infinite stop is smuggled into a fixed grid."""
    f = load_nq()
    f["volume"] = 0.0
    keep_load, keep_stop = V.load, V.STOPF.copy()
    V.load = lambda name: f
    if stopf is not None:
        V.STOPF[:] = stopf
    try:
        F = V.build("NQ")
        R, _amb = V.outcomes(F, COST_NQ, fillbar=1)
        risk, atr = V.risk_atr(F)
        mL, mS = V.filters(F)
    finally:
        V.load = keep_load
        V.STOPF[:] = keep_stop
    D = F["D"]
    R3 = R.reshape(D, len(V.IB_LEN), 2, 450)
    A = [np.ascontiguousarray(R3[:, :, s, :].reshape(D, V.NG)) * risk / atr for s in (0, 1)]
    P = [np.ascontiguousarray(R3[:, :, s, :].reshape(D, V.NG)) * risk for s in (0, 1)]
    Rr = [np.ascontiguousarray(R3[:, :, s, :].reshape(D, V.NG)) for s in (0, 1)]
    return F, A, P, Rr, mL, mS


def sel_days(F, mL, mS, c, stopf=None):
    """The days the rule trades, and its per-trade series."""
    keep = V.STOPF.copy()
    if stopf is not None:
        V.STOPF[:] = stopf
    try:
        g = gidx(c["ib"], c["retr"], c["stop"], c["tgt"], c["flat"])
    finally:
        V.STOPF[:] = keep
    ff = fidx(c["adx"], c["vol"], c["cpos"], c["ema"])
    si = 0 if c["side"] == "long" else 1
    li = g // 450
    msk = (mL if si == 0 else mS)[:, ff, li]
    return g, ff, si, li, msk


def score(A, P, Rr, g, si, days):
    a = A[si][days, g]
    p = P[si][days, g]
    r = Rr[si][days, g]
    w = p > 0
    return dict(n=len(days), atr=float(a.mean()), pts=float(p.mean()),
                pf=float(p[w].sum() / max(-p[~w].sum(), 1e-9)), win=float(w.mean() * 100),
                r=r, a=a, p=p)


def rows(F, A, P, Rr, mL, mS, c, stopf=None):
    g, ff, si, li, msk = sel_days(F, mL, mS, c, stopf)
    idx = np.arange(F["D"])
    days = idx[np.isfinite(A[si][idx, g]) & msk[idx]]
    if len(days) < 5:
        return None, days, g, si
    return score(A, P, Rr, g, si, days), days, g, si


def main():
    print("=" * 100)
    print("REVERSE-ENGINEERING THE INITIAL BALANCE EDGE -- NQ, the block that chose nothing")
    print("=" * 100)
    F, A, P, Rr, mL, mS = prep()
    base, days, g, si = rows(F, A, P, Rr, mL, mS, CLUSTER)
    print(f"  the cluster as declared: IB {CLUSTER['ib']}m, long, entry {CLUSTER['retr']}, "
          f"stop {CLUSTER['stop']}, no target, flat 15:55,")
    print(f"  {CLUSTER['adx']} + {CLUSTER['vol']} + {CLUSTER['cpos']} + {CLUSTER['ema']}")
    print(f"  n {base['n']}   {base['atr']:+.4f} ATR/trade   {base['pts']:+.2f} pts   "
          f"PF {base['pf']:.3f}   win {base['win']:.1f}%")

    # ---------------------------------------------------------------- 1. exit split
    print("\n" + "=" * 100)
    print("1. EXIT SPLIT -- a rule earning at the TIME exit is a direction bet, not a barrier edge")
    print("=" * 100)
    stopped = base["r"] <= -0.98
    print(f"  {'exit':<22}{'n':>5}{'share':>8}{'ATR/tr':>10}{'total ATR':>12}"
          f"{'share of net':>14}")
    tot = base["a"].sum()
    for nm, m in (("stop hit", stopped), ("flatten 15:55", ~stopped)):
        if m.sum() == 0:
            continue
        print(f"  {nm:<22}{int(m.sum()):>5d}{m.mean() * 100:>7.1f}%"
              f"{base['a'][m].mean():>+10.4f}{base['a'][m].sum():>+12.3f}"
              f"{base['a'][m].sum() / tot * 100:>13.1f}%")

    # ---------------------------------------------------------------- 2. infinite stop
    print("\n" + "=" * 100)
    print("2. WIDEN THE STOP UNTIL THE BARRIERS STOP BINDING")
    print("=" * 100)
    print(f"  {'stop (fraction of IB range)':<32}{'n':>5}{'ATR/tr':>10}{'pts/tr':>10}"
          f"{'PF':>8}{'win':>8}{'stopped out':>13}")
    for label, sv in (("0.40", 0.40), ("0.60", 0.60), ("0.80", 0.80), ("1.00  <- shipped", 1.00),
                      ("1.30", 1.30)):
        cc = dict(CLUSTER, stop=sv)
        r_, d_, g_, s_ = rows(F, A, P, Rr, mL, mS, cc)
        if r_ is None:
            continue
        st = (r_["r"] <= -0.98).mean() * 100
        print(f"  {label:<32}{r_['n']:>5d}{r_['atr']:>+10.4f}{r_['pts']:>+10.2f}"
              f"{r_['pf']:>8.3f}{r_['win']:>7.1f}%{st:>12.1f}%")
    inf_stop = np.array([0.40, 0.60, 0.80, 1.00, 1000.0])
    Fi, Ai, Pi, Ri, mLi, mSi = prep(inf_stop)
    ci = dict(CLUSTER, stop=1000.0)
    r_inf, d_inf, g_inf, s_inf = rows(Fi, Ai, Pi, Ri, mLi, mSi, ci, inf_stop)
    st = (r_inf["r"] <= -0.98).mean() * 100
    print(f"  {'INFINITE (no stop at all)':<32}{r_inf['n']:>5d}{r_inf['atr']:>+10.4f}"
          f"{r_inf['pts']:>+10.2f}{r_inf['pf']:>8.3f}{r_inf['win']:>7.1f}%{st:>12.1f}%")
    print(f"\n  the shipped 1.00 stop is worth {base['atr'] - r_inf['atr']:+.4f} ATR/trade against "
          f"no stop at all.")

    # ---------------------------------------------------------------- 3. day vs bar
    print("\n" + "=" * 100)
    print("3. DAY VERSUS BAR -- same days, same geometry, RANDOM entry time")
    print("=" * 100)
    p_ctrl, med, dist = control_p(F, g, si, days, COST_NQ, base["atr"])
    print(f"  rule {base['atr']:+.4f} ATR/trade   vs   random-entry control median {med:+.4f}"
          f"   p {p_ctrl:.4f}   over {len(dist)} draws")
    print("  (the control keeps the side, the geometry, the costs and the SAME 48 DAYS; only the")
    print("   entry moment is randomised, so it prices drift, barrier width and session timing.)")

    # ---------------------------------------------------------------- 4. what the days do
    print("\n" + "=" * 100)
    print("4. WHAT DO THE SELECTED DAYS DO ON THEIR OWN? -- the session-picker test")
    print("=" * 100)
    li = g // 450
    # session travel: the IB close to the flatten close, in ATR units at the plan bar.
    # `ibe` and `fend` are ABSOLUTE bar indices into the flat series, not per-day offsets.
    fend = F["fend"][:, int(np.flatnonzero(V.FLAT == CLUSTER["flat"])[0])]
    trav = np.full(F["D"], np.nan)
    for d in range(F["D"]):
        b0, b1 = int(F["ibe"][d, li]), int(fend[d])
        if b1 > b0 >= 1 and np.isfinite(F["atr"][d, li]) and F["atr"][d, li] > 0:
            trav[d] = (F["c"][b1 - 1] - F["c"][b0 - 1]) / F["atr"][d, li]
    allm = np.isfinite(trav)
    selm = np.zeros(F["D"], bool)
    selm[days] = True
    print(f"  {'group':<28}{'days':>6}{'mean travel':>14}{'median':>10}{'share up':>10}")
    for nm, m in (("the 48 selected days", allm & selm), ("every other day", allm & ~selm)):
        print(f"  {nm:<28}{int(m.sum()):>6d}{np.nanmean(trav[m]):>+14.4f}"
              f"{np.nanmedian(trav[m]):>+10.4f}{(trav[m] > 0).mean() * 100:>9.1f}%")
    print("  travel = IB close to 15:55 close, in ATR units at the plan bar. If the selected days")
    print("  simply drift up, the four conditions are a session picker and not an entry rule.")

    # ---------------------------------------------------------------- 5. drop-one and alone
    print("\n" + "=" * 100)
    print("5. WHICH CONDITION CREATES THE EDGE -- each dropped, then each on its own")
    print("=" * 100)
    print(f"  {'rule':<34}{'n':>5}{'ATR/tr':>10}{'pts/tr':>10}{'PF':>8}"
          f"{'win':>8}{'vs full':>10}{'ctrl p':>9}")

    def line(label, cc, ref=None):
        r_, d_, g_, s_ = rows(F, A, P, Rr, mL, mS, cc)
        if r_ is None:
            print(f"  {label:<34}   -- fewer than 5 trades --")
            return None
        pv = control_p(F, g_, s_, d_, COST_NQ, r_["atr"])[0] if len(d_) >= 15 else np.nan
        delta = "" if ref is None else f"{r_['atr'] - ref:>+10.4f}"
        print(f"  {label:<34}{r_['n']:>5d}{r_['atr']:>+10.4f}{r_['pts']:>+10.2f}"
              f"{r_['pf']:>8.3f}{r_['win']:>7.1f}%{delta:>10}{pv:>9.3f}")
        return r_

    line("FULL RULE (all four)", CLUSTER)
    line("none (geometry only)", dict(CLUSTER, adx="off", vol="off", cpos="off", ema="off"),
         base["atr"])
    print("  --- drop one " + "-" * 74)
    for k in COND:
        line(f"without {CLUSTER[k]}", dict(CLUSTER, **{k: "off"}), base["atr"])
    print("  --- alone " + "-" * 77)
    for k in COND:
        off = {j: "off" for j in COND if j != k}
        line(f"{CLUSTER[k]} only", dict(CLUSTER, **off), base["atr"])

    # ---------------------------------------------------------------- 6. the ladder
    print("\n" + "=" * 100)
    print("6. THE LADDER -- every rung of every condition, the rest held at the cluster")
    print("=" * 100)
    print("  A real mechanism decays smoothly across its own axis. A threshold that works at one")
    print("  setting and nowhere near it is a spike, not a mechanism.")
    print(f"  {'axis':<8}{'setting':<16}{'n':>5}{'ATR/tr':>10}{'pts/tr':>10}{'PF':>8}{'win':>8}")
    for k in COND:
        for v in LADDER[k]:
            cc = dict(CLUSTER, **{k: v})
            r_, d_, g_, s_ = rows(F, A, P, Rr, mL, mS, cc)
            if r_ is None:
                print(f"  {k:<8}{v:<16}   -- fewer than 5 trades --")
                continue
            mark = "  <-- shipped" if v == CLUSTER[k] else ""
            print(f"  {k:<8}{v:<16}{r_['n']:>5d}{r_['atr']:>+10.4f}{r_['pts']:>+10.2f}"
                  f"{r_['pf']:>8.3f}{r_['win']:>7.1f}%{mark}")
        print("  " + "-" * 62)


    # ---------------------------------------------------------------- 7. the geometry ladder
    print("\n" + "=" * 100)
    print("7. THE GEOMETRY LADDER, UNCONDITIONAL -- if the geometry is the edge, sweep it")
    print("=" * 100)
    print("  All four conditions OFF, one geometry axis moved at a time from the cluster's values.")
    print(f"  {'axis':<10}{'setting':<12}{'n':>6}{'ATR/tr':>10}{'pts/tr':>10}"
          f"{'PF':>8}{'win':>8}{'ctrl p':>9}")
    geom_only = dict(CLUSTER, adx="off", vol="off", cpos="off", ema="off")

    SHIPPED = {"IB length": 30, "retracement": 0.50, "stop": 1.00,
               "target": "none", "flatten": 955, "side": "long"}

    def gline(axis, label, cc):
        r_, d_, g_, s_ = rows(F, A, P, Rr, mL, mS, cc)
        if r_ is None:
            print(f"  {axis:<10}{label:<12}   -- too few --")
            return
        pv = control_p(F, g_, s_, d_, COST_NQ, r_["atr"])[0] if len(d_) >= 15 else np.nan
        mark = "  <-- shipped" if label == SHIPPED[axis] else ""
        print(f"  {axis:<10}{str(label):<12}{r_['n']:>6d}{r_['atr']:>+10.4f}"
              f"{r_['pts']:>+10.2f}{r_['pf']:>8.3f}{r_['win']:>7.1f}%{pv:>9.3f}{mark}")

    for v in V.IB_LEN:
        gline("IB length", int(v), dict(geom_only, ib=int(v)))
    print("  " + "-" * 73)
    for v in V.RETR:
        gline("retracement", float(v), dict(geom_only, retr=float(v)))
    print("  " + "-" * 73)
    for v in V.STOPF:
        gline("stop", float(v), dict(geom_only, stop=float(v)))
    print("  " + "-" * 73)
    for v in V.TGT:
        gline("target", "none" if v > 90 else float(v), dict(geom_only, tgt=float(v)))
    print("  " + "-" * 73)
    for v in V.FLAT:
        gline("flatten", int(v), dict(geom_only, flat=int(v)))
    print("  " + "-" * 73)
    gline("side", "long", geom_only)
    gline("side", "short", dict(geom_only, side="short"))

    print("\n" + "=" * 100)
    print("MULTIPLICITY, STATED RATHER THAN BURIED")
    print("=" * 100)
    print("  NQ was reserved as the block that chose nothing, and STUDY_V58 spent it on ONE read")
    print("  of a pre-declared cluster. This anatomy has read roughly SIXTY cells on it. Every")
    print("  p-value above is therefore descriptive, not pre-registered: they say which parts of")
    print("  the rule carry its result, and they no longer say the result is significant. The next")
    print("  test of anything found here needs a block none of this touched.")


if __name__ == "__main__":
    main()
