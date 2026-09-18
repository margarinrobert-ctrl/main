"""Family ablation, the second null, ONE holdout read, and the deflation.

The meta layer is the RIDGE -- it won the ladder outright and it is the only form that can be
written into Pine. Everything here is decided on research; the holdout is opened exactly once at
the end, at a keep fraction and a threshold both fixed beforehand.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpdon as D  # noqa: E402
from vpus30.run_d2 import build_all, EX_N, SL  # noqa: E402
from vpus30.run_d3 import oof, ic  # noqa: E402
sys.path.append("/root/.claude/skills/synced/"
                "a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/"
                "mechanism-first-alpha/scripts")
import gates  # noqa: E402

RNG = np.random.default_rng(90909)
BAR = "=" * 96
KEEP = 0.5          # fixed before the holdout is opened: the strongest rung that also clears


def fam(c):
    return c.split(".")[0] if "." in c else "vp"


def day_boot(r, ts, nb=2000):
    """Day-block bootstrap of the mean -- trades cluster inside a session."""
    d = pd.Series(r, index=pd.DatetimeIndex(ts).normalize())
    grp = [v.to_numpy() for _, v in d.groupby(level=0)]
    out = np.empty(nb)
    for i in range(nb):
        pick = RNG.integers(0, len(grp), len(grp))
        out[i] = np.nanmean(np.concatenate([grp[j] for j in pick]))
    return out


def main():
    f, g, cut, X, t, best_d = build_all()
    pool = list(np.load("research/vpus30/don_pool_final.npy", allow_pickle=True))
    ts = pd.DatetimeIndex(t.ts)
    res = np.asarray(ts < cut)
    sig, sd, y = t.sig.to_numpy(), t.side.to_numpy(), t.pct.to_numpy()
    E = X.iloc[sig][pool].reset_index(drop=True)
    Xm = E.to_numpy(float)
    med = np.nanmedian(Xm[res], axis=0)
    Xm = np.where(np.isfinite(Xm), Xm, med)
    Xr, yr = Xm[res], y[res]
    mk = lambda: Ridge(alpha=10.0)

    # ---- family ablation, 8 seeds
    print(BAR + "\nFAMILY ABLATION -- drop one family, 8 seeds\n" + BAR)
    fams = sorted({fam(c) for c in pool})
    full = np.array([ic(oof(Xr, yr, mk), yr)])
    base_ic = float(full[0])
    print(f"  all {len(pool)} features: IC {base_ic:.4f}   families {fams}")
    print(f"{'drop':<8}{'k':>5}{'IC':>9}{'delta':>9}")
    keepfam = []
    for fm in fams:
        cols = [i for i, c in enumerate(pool) if fam(c) != fm]
        v = ic(oof(Xr[:, cols], yr, mk), yr)
        print(f"{fm:<8}{len(cols):>5}{v:>9.4f}{v - base_ic:>9.4f}")
        if v < base_ic:
            keepfam.append(fm)
    print(f"  load-bearing (dropping HURTS): {keepfam}")

    # best subset = the load-bearing families only
    sub = [i for i, c in enumerate(pool) if fam(c) in keepfam] or list(range(len(pool)))
    sub_ic = ic(oof(Xr[:, sub], yr, mk), yr)
    print(f"  load-bearing subset only ({len(sub)} features): IC {sub_ic:.4f}")
    use = sub if sub_ic > base_ic else list(range(len(pool)))
    names = [pool[i] for i in use]
    print(f"  SHIPPING {len(use)} features, research IC {max(sub_ic, base_ic):.4f}")

    # ---- research threshold, fixed now
    p_r = oof(Xr[:, use], yr, mk)
    thr = float(np.nanquantile(p_r, 1 - KEEP))
    m_r = p_r >= thr
    sr, dr = sig[res], sd[res]
    base_r, _ = D.walk_at(g, sr, dr, ex_n=EX_N, sl=SL)
    kept_r, _ = D.walk_at(g, sr[m_r], dr[m_r], ex_n=EX_N, sl=SL)
    print("\n" + BAR + "\nSECOND NULL -- day-block bootstrap on the research uplift\n" + BAR)
    bb, bk = day_boot(base_r, ts[res]), day_boot(kept_r, ts[res][m_r])
    print(f"  base   net% {np.nanmean(base_r):.4f}  PF {D.pf(base_r):.3f}"
          f"  P(mean<=0) {float((bb <= 0).mean()):.3f}")
    print(f"  kept   net% {np.nanmean(kept_r):.4f}  PF {D.pf(kept_r):.3f}"
          f"  P(mean<=0) {float((bk <= 0).mean()):.3f}")
    print(f"  uplift {np.nanmean(kept_r) - np.nanmean(base_r):+.4f}"
          f"  P(uplift<=0) {float((bk - bb <= 0).mean()):.3f}")

    # ---- fit once on research, apply to the holdout. ONE READ.
    print("\n" + BAR + f"\nHOLDOUT -- one read, keep {KEEP:.0%}, threshold fixed on research\n" + BAR)
    sc = StandardScaler().fit(Xr[:, use])
    mdl = mk().fit(sc.transform(Xr[:, use]), yr)
    p_h = mdl.predict(sc.transform(Xm[~res][:, use]))
    m_h = p_h >= thr
    sh, dh = sig[~res], sd[~res]
    base_h, _ = D.walk_at(g, sh, dh, ex_n=EX_N, sl=SL)
    kept_h, _ = D.walk_at(g, sh[m_h], dh[m_h], ex_n=EX_N, sl=SL)
    print(f"  CALIBRATION: kept {m_h.mean():.3f} against the {KEEP:.2f} it was set for")
    print(f"  base   n {np.isfinite(base_h).sum():>4}  net% {np.nanmean(base_h):.4f}"
          f"  PF {D.pf(base_h):.3f}")
    print(f"  kept   n {np.isfinite(kept_h).sum():>4}  net% {np.nanmean(kept_h):.4f}"
          f"  PF {D.pf(kept_h):.3f}")
    up_h = float(np.nanmean(kept_h) - np.nanmean(base_h))
    print(f"  uplift {up_h:+.4f}")
    ctl = np.empty(400)
    for i in range(400):
        pick = RNG.choice(len(sh), size=int(m_h.sum()), replace=False)
        r, _ = D.walk_at(g, sh[pick], dh[pick], ex_n=EX_N, sl=SL)
        ctl[i] = np.nanmean(r) if np.isfinite(r).sum() >= 5 else np.nan
    print(f"  random gate of the same size: median {np.nanmedian(ctl):.4f}"
          f"   p {float(np.nanmean(ctl >= np.nanmean(kept_h))):.3f}")
    bh = day_boot(kept_h, ts[~res][m_h])
    print(f"  kept P(mean<=0) {float((bh <= 0).mean()):.3f}"
          f"   total return kept {np.nansum(kept_h):.2f}% vs base {np.nansum(base_h):.2f}%")
    print(f"  IC on the holdout {ic(p_h, y[~res]):.4f}")

    # ---- deflation
    print("\n" + BAR + "\nDEFLATION\n" + BAR)
    N = 8 + 128 + 12 + 8 + 1        # primary cells + screen + gate2 + ablations + holdout
    r = kept_h[np.isfinite(kept_h)]
    srh = float(np.mean(r) / (np.std(r, ddof=1) + 1e-12))
    print(f"  counted looks {N}   per-trade Sharpe {srh:.4f}  n {len(r)}")
    try:
        d = gates.deflated_sharpe(srh, len(r), N, var_trials=0.0004,
                                  skew=float(pd.Series(r).skew()),
                                  kurtosis=float(pd.Series(r).kurtosis() + 3),
                                  avg_correlation=0.7)
        print(f"  {d}")
    except Exception as e:                                    # noqa: BLE001
        print(f"  deflated_sharpe: {e}")

    # ---- portable form: the ridge constants
    co = pd.DataFrame(dict(feat=names, mean=sc.mean_, scale=sc.scale_, coef=mdl.coef_))
    co["absw"] = co.coef.abs()
    co = co.sort_values("absw", ascending=False)
    co.to_csv("research/vpus30/don_ridge.csv", index=False)
    print("\n  largest ridge coefficients")
    print(co.head(12)[["feat", "coef"]].to_string(index=False,
          float_format=lambda x: f"{x:+.4f}"))
    print(f"  intercept {mdl.intercept_:+.6f}   threshold {thr:+.6f}")


if __name__ == "__main__":
    main()
