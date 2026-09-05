"""Do the Turtle features predict a 1:1 outcome? Redundancy first, then incremental information.

THE TARGET IS THE THING BEING TRADED, not a return. For each eligible bar: does price reach +1R
before -1R and before the session flatten? A win is 1, everything else 0 -- a timeout is NOT a win,
because a trade closed on the clock at breakeven does not pay the cost. That makes the label
exactly the quantity a 65%-at-1:1 target refers to.

REDUNDANCY BEFORE PREDICTION. 117 features built from three window lengths and a handful of spans
are not 117 independent bets; `STUDY_FEATURES.md` found 134 features collapsing to 28 principal
components. Any per-feature p-value has to be corrected for the number of INDEPENDENT tests, not
the number of columns, so the effective count is measured first.

SELECTION ON THE RESEARCH BLOCK ONLY. The locked block is read once, at the end, for whatever
survives. `STUDY_FEATURES.md` records what ranking over both blocks did: a family that failed
research at p 0.08 "passed" locked at p 0.02.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtlefeat")


def label_1to1(h, l, c, atr, mod, stop_k=1.0, win_lo=570, win_hi=720, cost_bp=0.9,
               min_minutes_left=60, resolved_only=True):
    """1 if +1R is reached before -1R; 0 if -1R first. NaN if unresolved or too near the flatten.

    TWO CORRECTIONS THAT THE FIRST VERSION OF THIS LABEL NEEDED, and the reason is worth keeping:
    counting a clock-flatten as a LOSS made the label a function of TIME REMAINING and BAR SPEED
    rather than of direction. Measured, that artifact was overwhelming -- `min_to_close` separated
    0.00% from 43.17% and volatility features 8.84% from 42.77%, because a bar near the close
    cannot reach the target and a fast bar resolves before the bell. Sixty-four of 117 features
    "passed" BH on what was really a stopwatch.

      min_minutes_left  bars with less than this much session left are DROPPED, not labelled
      resolved_only     a trade that never touches either barrier is NaN, not a loss

    What remains is the question actually being asked: given that this trade resolves, does it
    resolve at the target? That is the quantity a 65%-at-1:1 claim refers to.
    """
    n = len(c)
    y = np.full(n, np.nan)
    cf = cost_bp / 1e4
    elig = (mod >= win_lo) & (mod < win_hi) & np.isfinite(atr) & (atr > 0)
    for i in np.flatnonzero(elig):
        if i + 1 >= n:
            break
        px = c[i] * (1 + cf); rk = stop_k * atr[i]
        if rk <= 0:
            continue
        if win_hi - mod[i] < min_minutes_left:
            continue
        st, tg = px - rk, px + rk
        j = i + 1; out = np.nan
        while j < n and mod[j] < win_hi:
            if l[j] <= st:
                out = 0.0; break
            if h[j] >= tg:
                out = 1.0; break
            j += 1
        if np.isnan(out) and not resolved_only:
            out = 0.0
        y[i] = out
    return y


def redundancy(F, names=None, thresh=0.9, verbose=True):
    """Correlation structure: |rho| clusters, and the effective number of independent features."""
    names = names or sorted(F)
    M = np.vstack([F[k] for k in names])
    ok = np.all(np.isfinite(M), axis=0)
    X = M[:, ok]
    C = np.corrcoef(X)
    np.fill_diagonal(C, 0.0)
    # single-linkage clusters at |rho| >= thresh
    nf = len(names); seen = np.zeros(nf, bool); clusters = []
    for i in range(nf):
        if seen[i]:
            continue
        stack = [i]; comp = []
        while stack:
            a = stack.pop()
            if seen[a]:
                continue
            seen[a] = True; comp.append(a)
            stack += list(np.flatnonzero((np.abs(C[a]) >= thresh) & ~seen))
        clusters.append([names[j] for j in comp])
    ev = np.linalg.eigvalsh(np.corrcoef(X))[::-1]
    ev = ev[ev > 0]
    cum = np.cumsum(ev) / ev.sum()
    npc90 = int(np.searchsorted(cum, 0.90) + 1)
    npc95 = int(np.searchsorted(cum, 0.95) + 1)
    if verbose:
        multi = [c for c in clusters if len(c) > 1]
        print(f"  {nf} features on {ok.sum():,} complete bars")
        print(f"  |rho| >= {thresh}: {len(clusters)} clusters ({len(multi)} with >1 member), "
              f"largest {max(len(c) for c in clusters)}")
        print(f"  principal components for 90% of variance: {npc90};  for 95%: {npc95}")
        print(f"  mean |rho| between features: {np.abs(C).sum()/(nf*(nf-1)):.3f}")
        for c in sorted(multi, key=len, reverse=True)[:5]:
            print(f"    cluster of {len(c)}: {', '.join(c[:5])}{' ...' if len(c) > 5 else ''}")
    return dict(clusters=clusters, npc90=npc90, npc95=npc95, names=names, corr=C, mask=ok)


def separation(F, y, names=None, cut=None, verbose=True, top=15):
    """Per-feature: win rate in the top vs bottom decile of the feature, and a z-test on the gap."""
    names = names or sorted(F)
    rows = []
    base_all = np.nanmean(y)
    for k in names:
        x = F[k]
        m = np.isfinite(x) & np.isfinite(y)
        if cut is not None:
            m = m & cut
        if m.sum() < 500:
            continue
        xs, ys = x[m], y[m]
        if np.nanstd(xs) == 0:
            continue
        lo, hi = np.nanpercentile(xs, [10, 90])
        a, b = ys[xs <= lo], ys[xs >= hi]
        if len(a) < 100 or len(b) < 100:
            continue
        pa, pb = a.mean(), b.mean()
        se = np.sqrt(pa * (1 - pa) / len(a) + pb * (1 - pb) / len(b))
        z = (pb - pa) / se if se > 0 else 0.0
        rows.append(dict(feature=k, n=int(m.sum()), win_lo=100 * pa, win_hi=100 * pb,
                         gap=100 * (pb - pa), z=z, best=100 * max(pa, pb)))
    R = pd.DataFrame(rows).sort_values("z", key=np.abs, ascending=False)
    if verbose and len(R):
        print(f"\n  base rate over the block: {100*base_all:.2f}%   n={int(np.isfinite(y).sum()):,}")
        print(f"  {'feature':<28}{'n':>8}{'win bottom10%':>15}{'win top10%':>12}{'gap':>8}{'z':>8}")
        for r in R.head(top).itertuples():
            print(f"  {r.feature:<28}{r.n:>8,}{r.win_lo:>14.2f}%{r.win_hi:>11.2f}%"
                  f"{r.gap:>+8.2f}{r.z:>8.2f}")
    return R
