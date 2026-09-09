"""A2 -- attack the two A1 results.

A1 produced two numbers that do not look like this branch: a research-to-reserved correlation
transfer of +0.705, where the usual figure here is -0.03 to +0.2; and a mean-variance book
beating equal weight out of sample at paired p 0.009 and the 99.4th percentile of random
weightings. Both are exactly the shape a lucky single fit produces, so:

  1. SPLIT THE CORRELATION TRANSFER. A pair that is the SAME strategy on two indices is
     correlated in every block by construction. If the transfer lives only there it says
     nothing an allocator can use.
  2. DOES THE RESEARCH MEAN PREDICT THE RESERVED MEAN? Mean-variance's load-bearing input is
     mu, the noisiest quantity in portfolio construction. Measure it directly across legs.
  3. ABLATE THE COVARIANCE. w proportional to the clipped research mean, no covariance at all.
     If that does as well, Sigma is decoration and the result is a mean tilt.
  4. WALK IT FORWARD. One fit is one draw. Re-fit the weights at every rebalance on an
     expanding window and stitch the out-of-sample pieces, over the WHOLE history.
  5. SLIDE THE CUT. `STUDY_DL50`'s test: if the win exists only at one split date it is the
     date, not the scheme.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alloccore as C  # noqa: E402
from run_a1 import apply_w  # noqa: E402

pd.set_option("display.width", 220)
MIN_RES, MIN_RSV = 30, 10


def prep():
    legs = C.load()
    names = sorted(legs.keys())
    X, span = C.panel(legs, names)
    cut = C.research_cut(legs)
    isr = X.index <= cut
    use = [k for k in names
           if (X.loc[isr, k] != 0).sum() >= MIN_RES and (X.loc[~isr, k] != 0).sum() >= MIN_RSV]
    return X[use], span[use], use, cut


def w_meantilt(X):
    return C._norm(X.mean(axis=0).to_numpy())


def w_invvol_meantilt(X):
    mu = np.clip(X.mean(axis=0).to_numpy(), 0, None)
    s = X.std(axis=0, ddof=1).to_numpy()
    s = np.where(s > 0, s, np.inf)
    return C._norm(mu / s)


ALL = dict(C.SCHEMES, meantilt=w_meantilt, invvol_meantilt=w_invvol_meantilt)


def main():
    X, span, use, cut = prep()
    isr = X.index <= cut
    Xr, Xo, sr, so = X.loc[isr], X.loc[~isr], span.loc[isr], span.loc[~isr]
    lab = [f"{k[0]}/{k[1]}" for k in use]

    # ---- 1. is the correlation transfer trivial? -------------------------------------------
    print("=== 1. correlation transfer, split by whether the pair is the SAME strategy ===")
    Cr, Co = np.corrcoef(Xr.to_numpy(), rowvar=False), np.corrcoef(Xo.to_numpy(), rowvar=False)
    iu = np.triu_indices(len(use), 1)
    same = np.array([use[i][0] == use[j][0] for i, j in zip(*iu)])
    a, b = Cr[iu], Co[iu]
    for nm, m in (("all pairs", np.ones(len(a), bool)), ("SAME strategy", same),
                  ("DIFFERENT strategy", ~same)):
        if m.sum() < 3:
            continue
        print(f"{nm:20s} n={m.sum():3d}  research |rho| {np.abs(a[m]).mean():.4f}  "
              f"reserved |rho| {np.abs(b[m]).mean():.4f}  "
              f"corr {np.corrcoef(a[m], b[m])[0,1]:+.4f} P / "
              f"{sps.spearmanr(a[m], b[m]).statistic:+.4f} S  "
              f"sign kept {np.mean(np.sign(a[m]) == np.sign(b[m])):.3f}")

    # ---- 2. does the research mean predict the reserved mean? ------------------------------
    print("\n=== 2. mean-variance's load-bearing input: does mu transfer across legs? ===")
    mr, mo = Xr.mean(axis=0).to_numpy(), Xo.mean(axis=0).to_numpy()
    sr_, so_ = Xr.std(axis=0, ddof=1).to_numpy(), Xo.std(axis=0, ddof=1).to_numpy()
    print(pd.DataFrame(dict(leg=lab, res_mean=mr, rsv_mean=mo, res_sd=sr_, rsv_sd=so_,
                            res_sharpe=mr / sr_ * np.sqrt(252),
                            rsv_sharpe=mo / so_ * np.sqrt(252))).round(4).to_string(index=False))
    print(f"\ncorr(research mean, reserved mean) = {np.corrcoef(mr, mo)[0,1]:+.4f} P / "
          f"{sps.spearmanr(mr, mo).statistic:+.4f} S   sign kept {np.mean(np.sign(mr)==np.sign(mo)):.3f}")
    print(f"corr(research sd,   reserved sd)   = {np.corrcoef(sr_, so_)[0,1]:+.4f} P / "
          f"{sps.spearmanr(sr_, so_).statistic:+.4f} S")
    print(f"corr(research Sharpe, reserved Sharpe) = "
          f"{np.corrcoef(mr/sr_, mo/so_)[0,1]:+.4f} P / "
          f"{sps.spearmanr(mr/sr_, mo/so_).statistic:+.4f} S")

    # ---- 3. ablate the covariance ----------------------------------------------------------
    print("\n=== 3. drop-one on mean-variance: is Sigma doing anything? ===")
    de = apply_w(Xo, so, ALL["equal"](Xr))
    rows = []
    for nm, fn in ALL.items():
        w = fn(Xr)
        dr, do = apply_w(Xr, sr, w), apply_w(Xo, so, w)
        d = do - de
        bs = C.block_boot(d, seed=1)
        rows.append(dict(scheme=nm, res_sharpe=C.stats(dr)["sharpe"],
                         rsv_total=C.stats(do)["total"], rsv_sharpe=C.stats(do)["sharpe"],
                         rsv_ret_dd=C.stats(do)["ret_dd"],
                         vs_equal=d.mean(), p=float(np.mean(bs <= 0))))
    print(pd.DataFrame(rows).round(4).to_string(index=False))

    # ---- 4. walk it forward ----------------------------------------------------------------
    print("\n=== 4. walk-forward allocation: re-fit at every rebalance, stitch the OOS pieces ===")
    print("    (expanding window; the whole history, not just the post-cut block)")
    idx = X.index
    rng = np.random.default_rng(7)
    for reb, minhist in ((252, 504), (126, 504), (63, 504)):
        starts = list(range(minhist, len(idx), reb))
        if len(starts) < 3:
            continue
        out = {nm: [] for nm in list(ALL) + ["random"]}
        for s in starts:
            e = min(s + reb, len(idx))
            tr, te = slice(0, s), slice(s, e)
            Xt, Xv, sv = X.iloc[tr], X.iloc[te], span.iloc[te]
            live = (Xt != 0).sum(axis=0) >= MIN_RES
            if live.sum() < 3:
                continue
            cols = list(Xt.columns[live])
            for nm, fn in ALL.items():
                w = np.zeros(X.shape[1])
                w[[X.columns.get_loc(c) for c in cols]] = fn(Xt[cols])
                out[nm].append(apply_w(Xv, sv, w))
            w = np.zeros(X.shape[1])
            w[[X.columns.get_loc(c) for c in cols]] = rng.dirichlet(np.ones(len(cols)))
            out["random"].append(apply_w(Xv, sv, w))
        rows = []
        for nm, v in out.items():
            d = np.concatenate(v)
            rows.append(dict(rebal=reb, scheme=nm, **C.stats(d)))
        R = pd.DataFrame(rows)
        eq = R[R.scheme == "equal"].iloc[0]
        R["vs_equal_sharpe"] = R["sharpe"] - eq["sharpe"]
        print(R.round(4).to_string(index=False))
        print()

    # ---- 5. slide the cut ------------------------------------------------------------------
    print("=== 5. slide the split: does mean-variance win at every cut? ===")
    rows = []
    for frac in np.arange(0.40, 0.86, 0.05):
        k = int(len(idx) * frac)
        Xt, Xv, st, sv = X.iloc[:k], X.iloc[k:], span.iloc[:k], span.iloc[k:]
        live = (Xt != 0).sum(axis=0) >= MIN_RES
        cols = list(Xt.columns[live])
        r = dict(frac=round(frac, 2), cut=str(idx[k].date()), legs=len(cols))
        base = None
        for nm in ("equal", "invvol", "riskparity", "minvar", "meanvar", "meantilt"):
            w = np.zeros(X.shape[1])
            w[[X.columns.get_loc(c) for c in cols]] = ALL[nm](Xt[cols])
            d = apply_w(Xv, sv, w)
            s = C.stats(d)["sharpe"]
            if nm == "equal":
                base = s
            r[nm] = round(s - base, 3) if nm != "equal" else round(s, 3)
        rows.append(r)
    print("(equal = its own Sharpe; every other column = Sharpe MINUS equal weight)")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
