"""Stage 3: walk-forward, Monte Carlo, parameter surface, anomaly follow-through, importance.

Everything here operates on rules already frozen by stage 2. It answers the brief's remaining
validation sections and produces the numbers the final report quotes.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import data, features, labels, splits, discover, fast, validate, anomaly


def wf_table(d, C, days, cond, stop_k, rr, lo, hi, max_hold, within, n_folds=6):
    P = labels.precompute(d, stop_k, rr=rr, max_hold=max_hold, lo=lo, hi=hi)
    m = (d["mod"] >= lo) & (d["mod"] < hi)
    for c in cond.split(" AND "):
        m = m & C[c]
    rows = []
    fz = validate.Frozen("x", tuple(cond.split(" AND ")), stop_k, rr, max_hold, lo, hi)
    for f, tr, te in splits.walk_forward(d, n_folds=n_folds, max_hold=max_hold, within=within):
        s = fast.score_days(P, m, te, days, day_pools=fast._day_pools(P, te, days),
                            draws=200, min_days=8)
        ix = pd.DatetimeIndex(d["idx"])[te]
        rows.append(dict(fold=f, start=str(ix[0].date()), end=str(ix[-1].date()),
                         n=(s["n"] if s else 0), win=(s["win"] if s else np.nan),
                         ctrl=(s["ctrl_win"] if s else np.nan),
                         expR=(s["expR"] if s else np.nan),
                         p=(s["p_day"] if s else np.nan)))
    return pd.DataFrame(rows)


def main():
    d = data.bars(15); F = features.build(d); C = discover.conditions(F)
    B = splits.blocks(d); days = fast.day_index(d)
    res = pd.read_parquet("research/edgelab/_validated.parquet")
    pd.set_option("display.width", 240)

    print("=" * 100)
    print("WALK-FORWARD (brief 32) -- rolling purged folds over discovery+validation, TEST halves only")
    within = B["discovery"] | B["validation"]
    for _, r in res.head(5).iterrows():
        full = r["cond"]
        print(f"\n{full}")
        t = wf_table(d, C, days, full, r["stop"], r["rr"], int(r["win_lo"]), 660, 16, within)
        print(t.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        ok = t.dropna(subset=["expR"])
        if len(ok):
            print(f"  aggregate: {int(ok['n'].sum())} trades, mean E[R] {ok['expR'].mean():+.3f}, "
                  f"folds positive {int((ok['expR']>0).sum())}/{len(ok)}")

    print("\n" + "=" * 100)
    print("MONTE CARLO (brief 34) on the best out-of-sample candidate")
    best = res.sort_values("prod_expR", ascending=False).iloc[0]
    P = labels.precompute(d, best["stop"], rr=best["rr"], max_hold=16,
                          lo=int(best["win_lo"]), hi=660)
    m = (d["mod"] >= best["win_lo"]) & (d["mod"] < 660)
    for c in best["cond"].split(" AND "):
        m = m & C[c]
    oos = B["validation"] | B["production"]
    R = P["R"][np.flatnonzero(P["valid"] & m & oos)]
    print(f"  {best['cond']}")
    print(f"  out-of-sample trades: {len(R)}, total {R.sum():+.1f}R, mean {R.mean():+.3f}R")
    mc = validate.monte_carlo(R, n=20000)
    if mc:
        for k, v in mc.items():
            print(f"    {k:<14} {v:+.3f}")

    print("\n" + "=" * 100)
    print("PARAMETER SURFACE (brief 35) -- discovery, is it a plateau or a spike?")
    rows = []
    for s in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5):
        for rr in (0.75, 1.0, 1.25, 1.5, 2.0):
            Pp = labels.precompute(d, s, rr=rr, max_hold=16, lo=int(best["win_lo"]), hi=660)
            sc = fast.score_days(Pp, m, B["discovery"], days,
                                 day_pools=fast._day_pools(Pp, B["discovery"], days), draws=100)
            rows.append(dict(stop=s, rr=rr, n=sc["n"] if sc else 0,
                             win=sc["win"] if sc else np.nan,
                             expR=sc["expR"] if sc else np.nan))
    surf = pd.DataFrame(rows).pivot(index="stop", columns="rr", values="expR")
    print("  E[R] by stop (rows, xATR) and target (cols, R):")
    print(surf.to_string(float_format=lambda x: f"{x:+.3f}"))

    print("\n" + "=" * 100)
    print("ANOMALY FOLLOW-THROUGH (brief 15) -- the one positive family, out of sample")
    A = anomaly.build(F, d)
    W = (d["mod"] >= 420) & (d["mod"] < 660)
    lab, z = A["body"]
    m_an = W & (lab == anomaly.EXTREME) & (z > 0)
    Pa = labels.precompute(d, 1.5, rr=1.0, max_hold=16, lo=420, hi=660)
    for tag, blk in (("discovery", B["discovery"]), ("validation", B["validation"]),
                     ("production", B["production"])):
        s = fast.score_days(Pa, m_an, blk, days, day_pools=fast._day_pools(Pa, blk, days),
                            draws=400, min_days=10)
        if s:
            print(f"  extreme bullish body, {tag:<11} n={s['n']:>4} days={s['days']:>3} "
                  f"win {s['win']:>5.1f}%  ctrl {s['ctrl_win']:>5.1f}%  excess {s['excess']:>+5.1f}"
                  f"  E[R] {s['expR']:>+6.3f}  p {s['p_day']:.3f}")
        else:
            print(f"  extreme bullish body, {tag:<11} too few")


if __name__ == "__main__":
    main()
