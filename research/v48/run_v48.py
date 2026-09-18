"""V48 -- can a risk-premium / PEAD-analogue / release-clock feature set improve a Donchian breakout?

SEARCH ON US100, HOLD BACK US30. Models are fitted and compared on the US100 RESEARCH block with
purged embargoed CV; the US100 locked block and the whole of US30 are read ONCE at the end.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v46")
sys.path.insert(0, "research/v48")
import v48base as B         # noqa: E402
import v48feat as FT        # noqa: E402
import v48ml as ML          # noqa: E402

SPLIT = 0.65
KEEP = 0.50


def dataset(market, tf):
    P = B.prep(market, tf)
    T = B.trades(P)
    F = FT.build(P)
    names = sorted(F)
    X = np.column_stack([np.asarray(F[k], float)[T["sig"]] for k in names])
    y = T["R"]
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    return (X[ok], y[ok], T["sig"][ok], T["xb"][ok], names, P["n"])


def main():
    rng = np.random.default_rng(11)
    rows = []
    for tf in (15, 30, 60):
        X, y, sig, xb, names, nbar = dataset("US100L", tf)
        res = sig < int(nbar * SPLIT)
        Xr, yr, sr, br = X[res], y[res], sig[res], xb[res]
        print("\n" + "=" * 100)
        print(f"  US100 {tf}m   {len(y)} trades ({int(res.sum())} research / {int((~res).sum())} locked)"
              f"   {len(names)} features   baseline R/trade {yr.mean():+.4f}")
        print("=" * 100)
        oof, used, folds = ML.cv(Xr, yr, sr, br, n_folds=5)
        print(f"  purged CV: {len(folds)} folds, {int(used.sum())} of {len(yr)} trades scored "
              f"out-of-fold\n")
        print(f"  {'model':<8}{'OOF IC':>9}{'kept R':>10}{'base R':>10}{'lift':>9}"
              f"{'p vs random':>13}")
        best, best_lift = None, -1e9
        for m in ML.MODELS:
            p = oof[m][used]
            s = ML.score_filter(yr[used], p, KEEP, rng)
            print(f"  {m:<8}{s['ic']:>+9.4f}{s['kept_R']:>+10.4f}{s['base_R']:>+10.4f}"
                  f"{s['lift']:>+9.4f}{s['p_vs_random']:>13.3f}")
            rows.append(dict(market="US100L", tf=tf, block="research-CV", model=m, **s))
            if s["lift"] > best_lift:
                best, best_lift = m, s["lift"]
        print(f"\n  best on research CV: {best}")

        # ---- frozen: fit on ALL research, read the holdout and the held-back market ONCE
        from sklearn.preprocessing import StandardScaler
        sc = StandardScaler().fit(Xr)
        fn = ML.MODELS[best]
        for lab, Xt, yt in (("US100 LOCKED", X[~res], y[~res]),):
            pt, _ = fn(sc.transform(Xr), yr, sc.transform(Xt))
            s = ML.score_filter(yt, pt, KEEP, rng)
            print(f"  {lab:<16} n {len(yt):>5}  kept R {s['kept_R']:+.4f}  base {s['base_R']:+.4f}"
                  f"  lift {s['lift']:+.4f}  p vs random {s['p_vs_random']:.3f}  IC {s['ic']:+.4f}")
            rows.append(dict(market="US100L", tf=tf, block="LOCKED", model=best, **s))
        Xu, yu, su, bu, nm2, _n = dataset("US30L", tf)
        pu, _ = fn(sc.transform(Xr), yr, sc.transform(Xu))
        s = ML.score_filter(yu, pu, KEEP, rng)
        print(f"  {'US30 (unseen)':<16} n {len(yu):>5}  kept R {s['kept_R']:+.4f}  base {s['base_R']:+.4f}"
              f"  lift {s['lift']:+.4f}  p vs random {s['p_vs_random']:.3f}  IC {s['ic']:+.4f}")
        rows.append(dict(market="US30L", tf=tf, block="UNSEEN", model=best, **s))
    d = pd.DataFrame(rows)
    d.to_csv("results/v48/v48_ml.csv", index=False)
    return d


if __name__ == "__main__":
    main()
