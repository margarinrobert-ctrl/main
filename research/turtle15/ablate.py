"""Feature ablation on the 15-minute Turtle: every gate against a SELECTIVITY-MATCHED control.

WHY THE CONTROL IS THE WHOLE TEST. A gate that keeps a quarter of the breakouts will change total
dollars no matter what it does, so comparing net profit fails every restrictive gate. Comparing
per-trade edge passes every one, because discarding trades at random raises the mean of a
fat-tailed distribution roughly a quarter of the time. The only question that is not rigged is:
does this gate beat a RANDOM filter that discards the same proportion?

The control resamples the BASELINE trade population to the gate's own trade count, 4,000 times.
`p` is the fraction of those random filters that did at least as well as the real gate.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15")
import fastbars, mirror, feats  # noqa: E402


def setup(tf=15, atr_len=20):
    d = fastbars.bars(tf)
    _, si, cut = fastbars.sessions(tf)
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], atr_len)
    C = mirror.channels(d["h"], d["l"])
    F = feats.build(d, atr, C)
    return d, si, cut, atr, C, F


def stats(t):
    if t is None or not len(t):
        return dict(n=0, per=0.0, win=0.0, pf=0.0, net=0.0, dd=0.0, streak=0)
    p = t.pnl.to_numpy()
    eq = p.cumsum()
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]))
    s = k = 0
    for x in p:
        k = k + 1 if x <= 0 else 0
        s = max(s, k)
    gp, gl = p[p > 0].sum(), -p[p < 0].sum()
    return dict(n=len(p), per=float(p.mean()), win=float((p > 0).mean()),
                pf=float(gp / gl) if gl > 0 else np.inf, net=float(p.sum()), dd=dd, streak=int(s))


def control(base_pnl, k, draws=4000, rng=None):
    """Random filters keeping k of the baseline trades. Returns the mean-P&L null distribution."""
    rng = rng or np.random.default_rng(17)
    if k < 5 or k >= len(base_pnl):
        return None
    idx = np.argsort(rng.random((draws, len(base_pnl))), axis=1)[:, :k]
    return base_pnl[idx].mean(axis=1)


def sweep(block="research", tf=15, min_n=60, draws=4000, verbose=True):
    d, si, cut, atr, C, F = setup(tf)
    m0 = (si < cut) if block == "research" else (si >= cut)
    base = mirror.run(d, 1, m0, atr, C)
    b = stats(base)
    bp = base.pnl.to_numpy()
    rng = np.random.default_rng(17)
    rows = [dict(gate="BASELINE (no gate)", side="", keep=1.0, p=np.nan, **b)]
    for name, x in sorted(F.items()):
        fin = np.isfinite(x)
        if fin.sum() < 1000 or np.nanstd(x[fin]) == 0:
            continue
        for q, lab in ((50, "top50"), (75, "top25")):
            for direction in (1, -1):
                thr = np.nanpercentile(x[fin & m0], q if direction > 0 else 100 - q)
                g = (x >= thr) if direction > 0 else (x <= thr)
                t = mirror.run(d, 1, m0 & fin & g, atr, C)
                s = stats(t)
                if s["n"] < min_n:
                    continue
                c = control(bp, s["n"], draws=draws, rng=rng)
                p = float((c >= s["per"]).mean()) if c is not None else np.nan
                rows.append(dict(gate=f"{name} {'>=' if direction>0 else '<='} {thr:+.3f}",
                                 side=lab, keep=s["n"] / b["n"], p=p, **s))
    R = pd.DataFrame(rows).sort_values("per", ascending=False)
    if verbose:
        print(f"\n  NQ {tf}m {block}: baseline n={b['n']} {b['per']:+.2f} pts/trade PF {b['pf']:.2f}")
        print(f"  {'gate':<34}{'n':>6}{'keep':>7}{'pts/tr':>9}{'win':>7}{'PF':>6}{'maxDD':>8}{'strk':>6}{'p':>7}")
        for r in R.head(20).itertuples():
            print(f"  {r.gate:<34}{r.n:>6}{100*r.keep:>6.0f}%{r.per:>+9.2f}{100*r.win:>6.1f}%"
                  f"{r.pf:>6.2f}{r.dd:>8.0f}{r.streak:>6}"
                  f"{('%.4f' % r.p) if np.isfinite(r.p) else '--':>7}")
        ok = R.p.notna()
        print(f"\n  gates beating their selectivity control at p<0.05: "
              f"{(R.p < 0.05).sum()}/{ok.sum()}  ({0.05*ok.sum():.1f} expected by chance)")
    return R
