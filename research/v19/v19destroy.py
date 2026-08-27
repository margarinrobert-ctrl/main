"""Trying to destroy the one rule that replicated. Overlap, cost, control, regime, time.

THE RESULT THAT HAS TO BE ATTACKED FIRST. The frozen rule scores +0.196 R on US100 and loses on
US30, on 8.5 years of US30 and on 22 years of gold. One market in four. And the one that works is
the NASDAQ-100 -- the same index the rule was found on. This branch has already established that a
second feed of the SAME INDEX over an OVERLAPPING calendar is not a second test: 68% of NQ's
triggers once fired on the identical 15-minute bar of US100. So the first question is not whether
US100 confirms the rule, it is whether US100 is independent evidence at all.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v19")
import v16core as C          # noqa: E402
import v19frozen as F        # noqa: E402

RNG = np.random.default_rng(20260828)


def overlap(a="NQ", b="US100"):
    """What share of a's signal BARS are also signal bars on b, at the same timestamp?"""
    Pa, Pb = F.ctx(a), F.ctx(b)
    Oa, ia = F.run(Pa)
    Ob, ib = F.run(Pb)
    ta = pd.to_datetime(Pa["ts"][Oa["sig"][ia]])
    tb = pd.to_datetime(Pb["ts"][Ob["sig"][ib]])
    lo, hi = max(ta.min(), tb.min()), min(ta.max(), tb.max())
    ta_o = ta[(ta >= lo) & (ta <= hi)]
    tb_o = tb[(tb >= lo) & (tb <= hi)]
    sb = set(tb_o)
    exact = np.mean([t in sb for t in ta_o]) if len(ta_o) else np.nan
    arr = np.sort(np.array(tb_o, dtype="datetime64[ns]").astype(np.int64))
    near = 0
    tol = 2 * 15 * 60 * 1_000_000_000
    for t in np.array(ta_o, dtype="datetime64[ns]").astype(np.int64):
        k = np.searchsorted(arr, t)
        cand = arr[max(0, k - 1):k + 2]
        if len(cand) and np.min(np.abs(cand - t)) <= tol:
            near += 1
    return dict(span=f"{lo.date()} to {hi.date()}", n_a=len(ta_o), n_b=len(tb_o),
                exact=exact, near=near / max(len(ta_o), 1))


def period_split(name, cut):
    """Split one market at a date and score each side separately."""
    P = F.ctx(name)
    ts = pd.to_datetime(P["ts"])
    pre = np.asarray(ts < cut)
    post = np.asarray(ts >= cut)
    out = {}
    for lab, blk in (("overlaps NQ", pre), ("after NQ ends", post)):
        O, i = F.run(P, block=blk)
        out[lab] = F.metrics(P, O, i, blk)
    return out


def zero_cost(name):
    """Is the failure a cost problem or an edge problem? Run at zero friction and see."""
    P = F.ctx(name)
    full = np.ones(len(P["c"]), bool)
    a, ia = F.run(P)
    b, ib = F.run(P, cost_mult=0.0)
    return F.metrics(P, a, ia, full), F.metrics(P, b, ib, full)


def control(P, block, O, idx, stop, draws=1500):
    if len(idx) < 15:
        return np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(block & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    Oa = C.outcomes(P, 1, elig.astype(np.int64), stop_mult=stop, tp_r=0.0)
    pos = {v: i for i, v in enumerate(elig)}
    real = float(O["R"][idx].sum())
    tot = np.empty(draws)
    for d in range(draws):
        pick = np.concatenate([RNG.choice(by[m], size=min(k, len(by[m])), replace=False)
                               for m, k in want.items() if len(by[m])])
        keep = np.zeros(len(elig), bool)
        keep[[pos[v] for v in np.sort(pick)]] = True
        tot[d] = Oa["R"][C.take(Oa, keep)].sum()
    return tot, float((tot >= real).mean())


if __name__ == "__main__":
    print("=" * 118)
    print("A. IS US100 INDEPENDENT EVIDENCE, OR IS IT NQ WITH A DIFFERENT TICKER?")
    print("=" * 118)
    ov = overlap("NQ", "US100")
    print(f"   overlapping span {ov['span']}   NQ signals {ov['n_a']}   US100 signals {ov['n_b']}")
    print(f"   NQ signal bars that are ALSO US100 signal bars, same timestamp : {ov['exact']:.1%}")
    print(f"   ... within +/- 2 bars                                          : {ov['near']:.1%}")
    print("\n   The rule fires on the same index at nearly the same moments. Over the overlap this")
    print("   is the same trade twice, not a confirmation. Only the part of US100 AFTER NQ's data")
    print("   ends is a test of anything.\n")
    sp = period_split("US100", pd.Timestamp("2025-12-12"))
    print(f"   {'US100 period':<20}{'n':>6}{'EV(R)':>9}{'PF':>8}{'net R':>9}{'maxDD':>8}"
          f"{'Sharpe':>8}{'Sortino':>9}")
    for k, m in sp.items():
        print(f"   {k:<20}{m['n']:>6}{m['ev']:>+9.4f}{m['pf']:>8.3f}{m['net']:>+9.1f}"
              f"{m['dd']:>8.1f}{m['sharpe']:>8.2f}{m['sortino']:>9.2f}")

    print("\n" + "=" * 118)
    print("B. WHY DOES IT FAIL ELSEWHERE? -- cost, or no edge? Run the zero-cost variant")
    print("=" * 118)
    print("   If a rule is negative at ZERO friction it does not have an edge that costs are")
    print("   eating; it has no edge. Always run this before blaming execution.\n")
    print(f"   {'market':<8}{'n':>7}{'EV with costs':>15}{'EV at zero cost':>17}"
          f"{'PF with':>9}{'PF zero':>9}{'cost as % of stop':>20}")
    for k in ("US30", "US100", "US30L", "XAU"):
        a, b = zero_cost(k)
        P = F.ctx(k)
        rt = float(P["fee2"] + np.nanmedian(P["f_taker"]) + np.nanmedian(P["f_stop"]))
        pct = 100 * rt / (2.5 * float(np.nanmedian(P["atr"])))
        print(f"   {k:<8}{a['n']:>7}{a['ev']:>+15.4f}{b['ev']:>+17.4f}"
              f"{a['pf']:>9.3f}{b['pf']:>9.3f}{pct:>19.1f}%")

    print("\n" + "=" * 118)
    print("C. THE MATCHED CONTROL ON EVERY MARKET")
    print("=" * 118)
    print(f"   {'market':<8}{'n':>7}{'rule R':>10}{'control med':>13}{'control p95':>13}"
          f"{'p':>8}   reading")
    for k in ("US30", "US100", "US30L", "XAU", "NQ"):
        P = F.ctx(k)
        full = np.ones(len(P["c"]), bool)
        O, i = F.run(P)
        ctl, p = control(P, full, O, i, F.FROZEN["stop"])
        r = float(O["R"][i].sum())
        v = ("beats control" if p <= 0.0125 else "beats at 5% (not Bonferroni)" if p <= 0.05
             else "NOT distinguishable")
        print(f"   {k:<8}{len(i):>7}{r:>+10.1f}{np.median(ctl):>+13.1f}"
              f"{np.percentile(ctl,95):>+13.1f}{p:>8.3f}   {v}")
    print("\n   Bonferroni for four pre-registered markets is 0.0125.")
