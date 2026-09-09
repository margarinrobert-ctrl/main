"""IS MOVEMENT FORECASTABLE ON US30 15m, AND IS DIRECTION STILL NOT?

Eight declared targets x three horizons x 100 causal features (71 volatility + a declared
inefficiency family), on the research block only, with DIRECTION carried as the control that must
fail. Every target is scored against the bar `STUDY_V28` set: the TRAILING REALISATION of that same
target, because nothing on this branch has ever beaten simply reading the current value.

THE NULL IS THE WHOLE METHOD AND IT IS EXACT HERE. Each reported |IC| is the MAXIMUM OVER 100
FEATURES, which no single shuffled twin can price, and the targets are built on OVERLAPPING windows
so a free permutation is far too easy (`STUDY_V67`: its p95 sat at ~0.014 for every target
regardless of persistence and 32 of 32 cells cleared it, direction included).

A CIRCULAR SHIFT of the target preserves its ENTIRE autocorrelation function exactly -- it is the
same vector -- and destroys only its alignment with the features. And every shift can be evaluated
at once: the circular cross-correlation of two standardised series is `irfft(conj(rfft(x)) *
rfft(y)) / n`, so one FFT per feature gives that feature's IC at ALL n shifts. Taking the max over
features at each shift gives the exact null distribution of the statistic actually being reported,
over ~180,000 draws instead of a few hundred, at less cost than the naive loop.

Shifts within +/-5,000 bars (~7 weeks) of zero are excluded, since a persistent target is still
partly aligned with itself there.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mv30 import mv30core as C  # noqa: E402
from v67 import v67core as V67  # noqa: E402

EXCL = 5000


def zrank(a):
    """Rank-transform then standardise, so a correlation is a Spearman IC."""
    r = pd.Series(a).rank().to_numpy()
    r = r - r.mean()
    s = r.std()
    return r / s if s > 0 else np.zeros_like(r)


def ic_all_shifts(Xz, yz):
    """(n_shifts,) max over features of |IC| at every circular shift, plus the per-shift argmax."""
    n = len(yz)
    fy = np.fft.rfft(yz)
    best = np.zeros(n)
    for j in range(Xz.shape[1]):
        cc = np.fft.irfft(np.conj(np.fft.rfft(Xz[:, j])) * fy, n) / n
        np.maximum(best, np.abs(cc), out=best)
    return best


def main():
    f = C.frame("US30L")
    blk = M_blocks = __import__("mr30.mr30core", fromlist=["x"]).blocks(f)
    res = blk["A_research"]
    X = C.features(f)
    cols = list(X.columns)

    print("TRUNCATION AUDIT on a sample of the pool (recompute from history ending at bar i)")
    bad, tot = C.truncation_audit(f, cols[::7], probes=8)
    print(f"  {bad} mismatches of {tot} probes\n")

    D = C.D_of(f)
    print("MOVEMENT vs DIRECTION on US30 15m, research block. Best |IC| over 100 features,")
    print("against the trailing realisation of the same target, with an exact circular-shift null.")
    print(f"\n{'target':<8}{'h':>4}{'best |IC|':>11}{'feature':>22}{'baseline':>10}"
          f"{'null p95':>10}{'ratio':>8}{'p':>8}")
    rows = []
    for h in C.HORIZONS:
        T = V67.build_targets(D, h)
        B = V67.trailing_baseline(D, h)
        for t in C.TARGETS:
            y = T[t]
            m = res & np.isfinite(y)
            for cname in cols:
                m &= True
            idx = np.flatnonzero(m)
            idx = idx[idx >= 800]
            if len(idx) < 5000:
                continue
            sub = X.iloc[idx]
            keep = [c for c in cols if np.isfinite(sub[c].to_numpy()).mean() > 0.95]
            Xz = np.column_stack([zrank(np.nan_to_num(sub[c].to_numpy(),
                                                      nan=np.nanmedian(sub[c].to_numpy())))
                                  for c in keep])
            yz = zrank(y[idx])
            ics = (Xz.T @ yz) / len(yz)
            j = int(np.argmax(np.abs(ics)))
            obs = float(abs(ics[j]))
            base = abs(V67.ic(B[t][idx], y[idx])) if t in B else np.nan
            null = ic_all_shifts(Xz, yz)
            ok = np.ones(len(null), bool)
            ok[:EXCL] = False
            ok[-EXCL:] = False
            p95 = float(np.percentile(null[ok], 95))
            p = float(np.mean(null[ok] >= obs))
            print(f"{t:<8}{h:>4}{obs:>11.4f}{keep[j][:21]:>22}{base:>10.4f}"
                  f"{p95:>10.4f}{obs / max(p95, 1e-9):>8.2f}{p:>8.4f}")
            rows.append(dict(target=t, h=h, ic=obs, feat=keep[j], base=base, p95=p95, p=p))
        print()
    d = pd.DataFrame(rows)
    d.to_csv("research/mv30/m1_research.csv", index=False)
    print("SUMMARY -- mean best |IC| by target (movement families vs the direction control)")
    g = d.groupby("target").agg(ic=("ic", "mean"), base=("base", "mean"),
                                p95=("p95", "mean"), clears=("p", lambda x: int((x <= 0.05).sum())))
    g["ratio"] = g.ic / g.p95
    for t, r in g.sort_values("ratio", ascending=False).iterrows():
        print(f"  {t:<6} best|IC| {r.ic:.4f}   trailing baseline {r.base:.4f}   "
              f"null p95 {r.p95:.4f}   ratio {r.ratio:>5.2f}   clears {int(r.clears)}/3")


if __name__ == "__main__":
    main()
