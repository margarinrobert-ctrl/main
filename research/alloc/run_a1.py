"""A1 -- the legs, the split, correlation transfer, and five weighting schemes.

Order matters. The correlation transfer test comes BEFORE the schemes, because if a research
correlation matrix does not predict the reserved one then min-variance and risk parity are
fitting noise and the only defensible answer is equal weight. Running the schemes first and
reading the winner is how a covariance estimate gets credited with an edge it never had.

Two nulls: EQUAL WEIGHT, and a uniform draw from the same simplex.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alloccore as C  # noqa: E402

pd.set_option("display.width", 200)


def apply_w(X, span, w, renorm=True):
    """Daily book return. With renorm, weights are re-spread over the legs live that day --
    which is what a trader does; without it an absent leg is simply zero exposure."""
    W = np.tile(np.asarray(w, float), (len(X), 1))
    A = span.to_numpy().astype(float)
    W = W * A
    if renorm:
        s = W.sum(axis=1, keepdims=True)
        W = np.divide(W, s, out=np.zeros_like(W), where=s > 0)
    return (X.to_numpy() * W).sum(axis=1)


def main():
    legs = C.load()
    names = sorted(legs.keys())
    print(f"legs available: {len(names)}")

    # ---- A. the legs -----------------------------------------------------------------------
    rows = []
    for k in names:
        r, b = C.leg_daily(legs[k])
        m = b == legs[k]["is_block"]
        rows.append(dict(leg=f"{k[0]}/{k[1]}", n=int((legs[k]['tr']['pct'] != 0).sum()),
                         trades=len(legs[k]["tr"]),
                         first=r.index.min().date(), last=r.index.max().date(),
                         res_end=r.index[m].max().date() if m.any() else None,
                         res_days=int(m.sum()), rsv_days=int((~m).sum()),
                         tot=float(r.sum())))
    print("\n=== A. legs ===")
    print(pd.DataFrame(rows).to_string(index=False))

    cut = C.research_cut(legs)
    print(f"\ncommon research cut (every leg still in its own research block): {cut.date()}")

    X, span = C.panel(legs, names)
    isr = X.index <= cut
    print(f"book calendar {X.index.min().date()} .. {X.index.max().date()}  "
          f"research days {isr.sum()}  reserved days {(~isr).sum()}")

    # legs with no reserved activity at all cannot be allocated to out of sample
    live_rsv = [k for k in names if (X.loc[~isr, k] != 0).sum() >= 10]
    live_res = [k for k in names if (X.loc[isr, k] != 0).sum() >= 30]
    use = [k for k in names if k in live_rsv and k in live_res]
    print(f"legs with >=30 active research days and >=10 active reserved days: {len(use)}")
    for k in use:
        print(f"   {k[0]}/{k[1]}")
    if len(use) < 3:
        print("not enough legs to allocate across; stopping")
        return

    X = X[use]
    span = span[use]
    Xr, Xo = X.loc[isr], X.loc[~isr]
    sr, so = span.loc[isr], span.loc[~isr]

    # ---- B. correlation transfer -----------------------------------------------------------
    print("\n=== B. does the research correlation matrix predict the reserved one? ===")
    Cr = np.corrcoef(Xr.to_numpy(), rowvar=False)
    Co = np.corrcoef(Xo.to_numpy(), rowvar=False)
    iu = np.triu_indices(len(use), 1)
    a, b = Cr[iu], Co[iu]
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    print(f"pairs {len(a)}   research |rho| mean {np.abs(a).mean():.4f}   "
          f"reserved |rho| mean {np.abs(b).mean():.4f}")
    print(f"corr(research rho, reserved rho) = {np.corrcoef(a, b)[0,1]:+.4f} Pearson / "
          f"{sps.spearmanr(a, b).statistic:+.4f} Spearman")
    print(f"sign kept {np.mean(np.sign(a) == np.sign(b)):.3f}   mean |delta| {np.abs(a-b).mean():.4f}")
    print("\nresearch pairwise correlation:")
    print(pd.DataFrame(Cr, index=[f"{k[0][:6]}/{k[1][:5]}" for k in use],
                       columns=[f"{k[0][:6]}/{k[1][:5]}" for k in use]).round(3).to_string())

    # ---- C. schemes ------------------------------------------------------------------------
    print("\n=== C. five schemes, weights from RESEARCH ONLY, one reserved read ===")
    W, res = {}, []
    for nm, fn in C.SCHEMES.items():
        w = fn(Xr)
        W[nm] = w
        dr, do = apply_w(Xr, sr, w), apply_w(Xo, so, w)
        res.append(dict(scheme=nm, **{f"res_{a}": v for a, v in C.stats(dr).items()},
                        **{f"rsv_{a}": v for a, v in C.stats(do).items()}))
    R = pd.DataFrame(res)
    print(R[["scheme", "res_total", "res_per_yr", "res_sharpe", "res_ret_dd",
             "rsv_total", "rsv_per_yr", "rsv_sharpe", "rsv_dd", "rsv_ret_dd"]].round(4).to_string(index=False))

    print("\nweights:")
    print(pd.DataFrame(W, index=[f"{k[0]}/{k[1]}" for k in use]).round(4).to_string())

    # ---- D. paired test against equal weight -----------------------------------------------
    print("\n=== D. paired block bootstrap of the daily DIFFERENCE vs equal weight (reserved) ===")
    de = apply_w(Xo, so, W["equal"])
    for nm in C.SCHEMES:
        if nm == "equal":
            continue
        d = apply_w(Xo, so, W[nm]) - de
        bs = C.block_boot(d, seed=1)
        p = float(np.mean(bs <= 0))
        print(f"{nm:12s} mean daily diff {d.mean():+.6f}  P(<=0) {p:.3f}  "
              f"95% CI [{np.percentile(bs,2.5):+.6f}, {np.percentile(bs,97.5):+.6f}]")

    # ---- E. the random-weight null ---------------------------------------------------------
    print("\n=== E. random draws from the same simplex (reserved) ===")
    RW = C.rand_weights(len(use), n=2000, seed=2)
    rs = np.array([C.stats(apply_w(Xo, so, RW[i]))["sharpe"] for i in range(len(RW))])
    rt = np.array([C.stats(apply_w(Xo, so, RW[i]))["total"] for i in range(len(RW))])
    print(f"random reserved Sharpe: p5 {np.percentile(rs,5):+.3f}  median {np.median(rs):+.3f}  "
          f"p95 {np.percentile(rs,95):+.3f}")
    for nm in C.SCHEMES:
        d = apply_w(Xo, so, W[nm])
        s, t = C.stats(d)["sharpe"], C.stats(d)["total"]
        print(f"{nm:12s} reserved Sharpe {s:+.3f} at percentile {100*np.mean(rs < s):5.1f}   "
              f"total {t:+.3f} at percentile {100*np.mean(rt < t):5.1f}")


if __name__ == "__main__":
    main()
