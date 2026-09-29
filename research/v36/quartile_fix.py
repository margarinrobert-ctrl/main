"""The best-of-four-quartiles correction, and the validation read on whatever survives it.

PHASE 4 REPORTED 5 OF 11 FEATURES CLEARING p <= 0.05 AGAINST 0.6 EXPECTED. That comparison is
wrong and the error is mine: for each feature I search all four quartiles and report the BEST one,
so the statistic being tested is a MAXIMUM OF FOUR, while the control draws a single random subset.
A max-of-four beats a single draw far more often than 5% of the time under the null.

The corrected null does exactly what the search does: split the control draw into four groups of the
same sizes and take ITS best. Anything that still clears is worth a validation read; anything that
does not was an artifact of how the search was scored.
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
import indicators as I        # noqa: E402
import levels as LV           # noqa: E402
import setup as S             # noqa: E402
import engine as E            # noqa: E402
from run_base import splits            # noqa: E402
from run_filter import BASES, features  # noqa: E402


def max_quartile_control(R, sizes, draws=2000, seed=11):
    """Under the null: shuffle, cut into groups of the SAME sizes, take the best group mean --
    the same statistic the search maximises."""
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    n = len(R)
    for k in range(draws):
        p = rng.permutation(n)
        i = 0
        best = -1e18
        for s in sizes:
            m = R[p[i:i + s]].mean()
            if m > best:
                best = m
            i += s
        out[k] = best
    return out


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118, flush=True)


if __name__ == "__main__":
    d = LV.load()
    atrs = {p: I.ema(I.true_range(d["h"], d["l"], d["c"]), p) for p in (14, 20, 30)}
    pools = S.build_pools(d)
    ifv = {}
    for tf in (5, 15):
        r = S.htf_frame(d, tf)
        at = I.ema(I.true_range(r["h"], r["l"], r["c"]), 14)
        ifv[tf] = (r, S.find_ifvgs(r, S.find_fvgs(r, at)))

    for B in BASES:
        sl = S.find_sweeps(d, pools, +1, defn=B["defn"], atr=atrs[14])
        ss = S.find_sweeps(d, pools, -1, defn=B["defn"], atr=atrs[14])
        r, iv = ifv[B["tf"]]
        su = pd.concat([S.setups(d, +1, sl, iv, r, B["tf"]),
                        S.setups(d, -1, ss, iv, r, B["tf"])],
                       ignore_index=True).sort_values("inv_bar_1m").reset_index(drop=True)
        sb = su.inv_bar_1m.to_numpy(np.int64)
        tr, _i = E.run(d, su, atrs[B["atr_p"]][sb], entry=B["entry"], stop=B["stop"],
                       stop_k=B["stop_k"], stop_buf=0.25, tp="R", tp_r=B["tp_r"], retest_bars=60)
        X = features(d, su, atrs[14]).iloc[:len(tr)].reset_index(drop=True)
        blk = splits(d["tday"], tr.fill_bar.to_numpy())
        fin = np.isfinite(X.to_numpy()).all(axis=1)
        mt, mv = blk["train"] & fin, blk["valid"] & fin
        Rt, Rv = tr.R.to_numpy()[mt], tr.R.to_numpy()[mv]
        Xt, Xv = X[mt].reset_index(drop=True), X[mv].reset_index(drop=True)

        hdr(f"{B['tag']}   train n={len(Rt)} R {Rt.mean():+.4f}   valid n={len(Rv)} "
            f"R {Rv.mean():+.4f}")
        print(f"   {'feature':<14}{'Q':>3}{'n':>6}{'train R':>10}{'naive p':>10}"
              f"{'corrected p':>13}{'  ':>2}{'valid n':>9}{'valid R':>10}")
        rows = []
        for col in Xt.columns:
            if col.startswith("src_") or col == "side":
                continue
            q = pd.qcut(Xt[col], 4, labels=False, duplicates="drop")
            if q.isna().all():
                continue
            sizes = [int((q == i).sum()) for i in range(int(np.nanmax(q)) + 1)]
            means = [Rt[(q == i).to_numpy()].mean() if sizes[i] >= 25 else -1e18
                     for i in range(len(sizes))]
            bq = int(np.argmax(means))
            best = means[bq]
            if best < -1e17:
                continue
            # naive: a single random subset of the same size
            rng = np.random.default_rng(5)
            naive = np.array([Rt[rng.choice(len(Rt), sizes[bq], replace=False)].mean()
                              for _ in range(2000)])
            corr = max_quartile_control(Rt, sizes)
            # the same quartile edges applied to validation, never re-fitted
            edges = pd.qcut(Xt[col], 4, retbins=True, duplicates="drop")[1]
            qv = pd.cut(Xv[col], edges, labels=False, include_lowest=True)
            selv = (qv == bq).to_numpy()
            vr = Rv[np.nan_to_num(selv, nan=False).astype(bool)] if selv.any() else np.array([])
            rows.append(dict(feature=col, q=bq, n=sizes[bq], R=best,
                             p_naive=float((naive >= best).mean()),
                             p_corr=float((corr >= best).mean()),
                             vn=len(vr), vR=float(vr.mean()) if len(vr) else np.nan))
        fr = pd.DataFrame(rows).sort_values("R", ascending=False)
        for r_ in fr.itertuples():
            flag = "  <-- survives" if r_.p_corr <= 0.05 else ""
            print(f"   {r_.feature:<14}{r_.q:>3}{r_.n:>6}{r_.R:>+10.4f}{r_.p_naive:>10.3f}"
                  f"{r_.p_corr:>13.3f}{'  ':>2}{r_.vn:>9}"
                  f"{(r_.vR if np.isfinite(r_.vR) else float('nan')):>+10.4f}{flag}")
        print(f"\n   clearing the NAIVE control:     {int((fr.p_naive <= 0.05).sum())} of {len(fr)}")
        print(f"   clearing the CORRECTED control: {int((fr.p_corr <= 0.05).sum())} of {len(fr)}"
              f"   (expected by chance {0.05 * len(fr):.1f})")
        okv = fr.dropna(subset=["vR"])
        if len(okv):
            print(f"   of all {len(okv)} best-quartiles, still profitable on VALIDATION: "
                  f"{int((okv.vR > 0).sum())}   mean train {okv.R.mean():+.4f} -> "
                  f"mean valid {okv.vR.mean():+.4f}")
