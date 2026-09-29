"""V47 -- does the index drift or revert after a surprise, and do the premia predict anything.

TWO TESTS, both on the RESEARCH block first and the locked block read once.

  1. THE PEAD-ANALOGUE TEST. Sign the forward return by the surprise: mean of sign(SUE) x r_fwd.
     POSITIVE = drift, which is what PEAD describes. NEGATIVE = reversal. This branch's standing
     prior is reversal -- trend persistence has predicted negatively at every scale tested here,
     and five trend-following briefs have resolved into mean reversion -- so a positive result
     would be the surprising one and gets the harder look.

  2. INFORMATION COEFFICIENTS for all 30 features at four horizons. Spearman IC with a
     NEWEY-WEST t-statistic at lag = h, because k-day forward returns on daily bars overlap and a
     naive t treats 763 overlapping observations as independent when they are nothing like it.
     Benjamini-Hochberg at FDR 0.10 over the 120 research tests.

POWER, STATED BEFORE THE RESULTS: 763 sessions, 495 research and 268 locked. At h=20 the locked
block holds roughly 13 independent 20-day windows. That is enough to reject a large effect and
nowhere near enough to establish a small one, and no amount of decoration changes it.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v47")
import v47daily as DD       # noqa: E402
import v47feat as FT        # noqa: E402

HORIZONS = (1, 5, 10, 20)


def nw_t(x, lag):
    """Newey-West t for the mean of an overlapping series."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 20:
        return np.nan, np.nan, n
    m = x.mean()
    e = x - m
    g0 = float(e @ e) / n
    s = g0
    for L in range(1, min(lag, n - 1) + 1):
        gl = float(e[L:] @ e[:-L]) / n
        s += 2.0 * (1.0 - L / (lag + 1.0)) * gl
    se = np.sqrt(max(s, 1e-30) / n)
    return m, m / se, n


def bh(p, q=0.10):
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    idx = np.flatnonzero(ok)
    o = idx[np.argsort(p[idx])]
    m = len(o)
    keep = np.zeros(len(p), bool)
    thr = 0.0
    for r, i in enumerate(o, 1):
        if p[i] <= q * r / m:
            thr = p[i]
    if thr > 0:
        keep[ok] = p[ok] <= thr
    return keep, thr


def main():
    D = DD.build()
    F = FT.build(D)
    fwd = {h: DD.forward(D, h) for h in HORIZONS}
    res = D.research.to_numpy()

    # ---------------------------------------------------------------- 1. the PEAD-analogue test
    print("=" * 104)
    print("  1. DOES THE INDEX DRIFT OR REVERT AFTER A SURPRISE?   mean of sign(SUE) x forward return")
    print("     positive = DRIFT (what PEAD describes)   negative = REVERSAL")
    print("=" * 104)
    rows = []
    for sue_name in ("pead.sue", "pead.sue_on"):
        s = F[sue_name]
        for thr in (0.0, 1.0, 1.5, 2.0):
            for h in HORIZONS:
                fw = fwd[h]
                ev = np.isfinite(s) & (np.abs(s) >= thr) & np.isfinite(fw)
                for bname, blk in (("research", res), ("locked", ~res)):
                    m = ev & blk
                    if m.sum() < 25:
                        continue
                    signed = np.sign(s[m]) * fw[m]
                    mu, t, n = nw_t(signed, h)
                    rows.append(dict(sue=sue_name, thr=thr, h=h, block=bname, n=n,
                                     mean_bp=mu * 1e4, t=t,
                                     p=2 * (1 - stats.norm.cdf(abs(t))) if np.isfinite(t) else np.nan))
    P = pd.DataFrame(rows)
    P.to_csv("results/v47/v47_pead.csv", index=False)
    for sue_name in ("pead.sue", "pead.sue_on"):
        lab = "close-to-close surprise" if sue_name == "pead.sue" else "OVERNIGHT surprise (where a release lands)"
        print(f"\n  {lab}")
        print(f"    {'|SUE|>=':>8}{'h':>4}{'research n':>12}{'mean bp':>10}{'NW t':>8}"
              f"{'|':>3}{'locked n':>10}{'mean bp':>10}{'NW t':>8}{'  sign agrees?':>15}")
        for thr in (0.0, 1.0, 1.5, 2.0):
            for h in HORIZONS:
                a = P[(P.sue == sue_name) & (P.thr == thr) & (P.h == h) & (P.block == "research")]
                b = P[(P.sue == sue_name) & (P.thr == thr) & (P.h == h) & (P.block == "locked")]
                if not len(a) or not len(b):
                    continue
                a = a.iloc[0]; b = b.iloc[0]
                ag = "yes" if np.sign(a.mean_bp) == np.sign(b.mean_bp) else "NO"
                print(f"    {thr:>8.1f}{h:>4}{int(a.n):>12}{a.mean_bp:>+10.1f}{a.t:>+8.2f}"
                      f"{'|':>3}{int(b.n):>10}{b.mean_bp:>+10.1f}{b.t:>+8.2f}{ag:>15}")

    # ---------------------------------------------------------------- 2. the IC battery
    print("\n" + "=" * 104)
    print("  2. INFORMATION COEFFICIENTS -- 30 features x 4 horizons, Spearman, NW t at lag h")
    print("=" * 104)
    ic = []
    for k, arr in F.items():
        a = np.asarray(arr, float)
        for h in HORIZONS:
            fw = fwd[h]
            for bname, blk in (("research", res), ("locked", ~res)):
                m = blk & np.isfinite(a) & np.isfinite(fw)
                if m.sum() < 60 or np.nanstd(a[m]) == 0:
                    continue
                rho = stats.spearmanr(a[m], fw[m]).statistic
                # NW t on the per-observation IC contribution, ranks demeaned
                ra = stats.rankdata(a[m]); rf = stats.rankdata(fw[m])
                ra = (ra - ra.mean()) / ra.std(ddof=1); rf = (rf - rf.mean()) / rf.std(ddof=1)
                _mu, t, n = nw_t(ra * rf, h)
                ic.append(dict(feat=k, fam=k.split(".")[0], h=h, block=bname, n=int(m.sum()),
                               ic=rho, t=t,
                               p=2 * (1 - stats.norm.cdf(abs(t))) if np.isfinite(t) else np.nan))
    I = pd.DataFrame(ic)
    R = I[I.block == "research"].copy()
    keep, thr = bh(R.p.to_numpy(), 0.10)
    R["bh_pass"] = keep
    I.to_csv("results/v47/v47_ic.csv", index=False)
    print(f"\n  {len(R)} research tests. BH at FDR 0.10 -> threshold p <= {thr:.4f}, "
          f"{int(keep.sum())} pass (chance expects {0.10*len(R):.1f} false among any passers)")
    print(f"  largest |IC| anywhere on research: {R.ic.abs().max():.4f}")
    surv = R[R.bh_pass].sort_values("p")
    if len(surv):
        print(f"\n  {'feature':<22}{'h':>3}{'research IC':>13}{'NW t':>8}{'p':>9}"
              f"{'|':>3}{'LOCKED IC':>11}{'NW t':>8}{'  same sign?':>13}")
        for _, r in surv.iterrows():
            lk = I[(I.feat == r.feat) & (I.h == r.h) & (I.block == "locked")]
            if not len(lk):
                continue
            lk = lk.iloc[0]
            ag = "yes" if np.sign(r.ic) == np.sign(lk.ic) else "NO"
            print(f"  {r.feat:<22}{int(r.h):>3}{r.ic:>+13.4f}{r.t:>+8.2f}{r.p:>9.4f}"
                  f"{'|':>3}{lk.ic:>+11.4f}{lk.t:>+8.2f}{ag:>13}")
        n_ag = sum(1 for _, r in surv.iterrows()
                   for lk in [I[(I.feat == r.feat) & (I.h == r.h) & (I.block == "locked")]]
                   if len(lk) and np.sign(r.ic) == np.sign(lk.iloc[0].ic))
        print(f"\n  survivors keeping their SIGN on locked: {n_ag} of {len(surv)} "
              f"(chance expects {0.5*len(surv):.1f})")
    else:
        print("\n  NOTHING survives BH at FDR 0.10 on the research block.")
    return P, I


if __name__ == "__main__":
    main()
