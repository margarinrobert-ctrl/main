"""PHASE 4 -- the last live hypothesis: does ANY pre-entry conditioning isolate a profitable subset?

Phases 1-3 established that the setup has no expectancy and that the grid's maximum has no
neighbourhood and does not survive validation. What remains untested is the brief's sections 9, 10
and 11: a quality score, a chop/regime filter, and a time-of-day filter. Those SELECT among setups
rather than change the geometry, so they are the one route left that could rescue the concept.

THE BASE IS CHOSEN FROM THE MARGINAL AVERAGES, NOT FROM THE TOP CELL, so the filter test is not
conditioned on a corner that phase 3 already rejected: `close` sweep (best defn marginal), 15m (best
tf), `edge` entry (best entry), `max` stop (best stop), ATR 30, k 1.5, target 0.75R (best tp). The
train winner is run beside it so the answer does not depend on one base.

EVERY FEATURE IS AVAILABLE BEFORE ENTRY. Sweep source and magnitude, distance from session VWAP,
VWAP slope, ATR regime, realised-volatility regime, efficiency ratio, ADX, session range position,
minute of day, session, side, and the gap between sweep and inversion.

The gate is a same-selectivity control: keeping the best 25% of setups by any measure must beat
keeping a RANDOM 25%, because restrictiveness alone raises PF.
"""
from __future__ import annotations

import sys
import time
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
from run_base import splits, metrics   # noqa: E402
import lightgbm as lgb        # noqa: E402

BASES = [
    dict(tag="marginal-best", defn="close", tf=15, entry="edge", stop="max", atr_p=30,
         stop_k=1.5, tp_r=0.75),
    dict(tag="train winner", defn="pen_only", tf=15, entry="edge", stop="sweep", atr_p=14,
         stop_k=1.0, tp_r=1.5),
]


def hdr(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


def vwap_feats(d):
    """Session VWAP, its slope, and price distance from it in ATR. Cumulative within the RTH
    session only, so it never reads across a day boundary."""
    tp = (d["h"] + d["l"] + d["c"]) / 3.0
    inr = (d["tmin"] >= 930) & (d["tmin"] < 1320)
    key = pd.Series(np.where(inr, d["tday"], -1))
    pv = pd.Series(np.where(inr, tp * d["v"], 0.0)).groupby(key).cumsum()
    vv = pd.Series(np.where(inr, d["v"], 0.0)).groupby(key).cumsum()
    vwap = (pv / vv.replace(0, np.nan)).to_numpy()
    slope = pd.Series(vwap).diff(30).to_numpy()
    return vwap, slope


def features(d, su, atr1):
    sb = su.inv_bar_1m.to_numpy(np.int64)
    vwap, vslope = vwap_feats(d)
    c, h, l = d["c"], d["h"], d["l"]
    a = atr1[sb]
    _pdi, _mdi, adx = I.adx_di(h, l, c, 14)
    rv = pd.Series(np.r_[np.nan, np.diff(np.log(c))]).rolling(60).std().to_numpy()
    er = (np.abs(c - I.shift(c, 60)) /
          pd.Series(np.abs(np.r_[np.nan, np.diff(c)])).rolling(60).sum().to_numpy())
    atr_z = atr1 / I.sma(atr1, 500)
    X = pd.DataFrame(dict(
        pen_atr=su.pen_atr.to_numpy(),
        gap_bars=su.gap_bars.to_numpy(),
        side=su.side.to_numpy().astype(float),
        zone_atr=(su.zhi.to_numpy() - su.zlo.to_numpy()) / np.maximum(a, 1e-9),
        sweep_dist=np.abs(su.sweep_ext.to_numpy() - su.zhi.to_numpy()) / np.maximum(a, 1e-9),
        vwap_dist=(c[sb] - vwap[sb]) / np.maximum(a, 1e-9),
        vwap_slope=vslope[sb] / np.maximum(a, 1e-9),
        adx=adx[sb], rvol=rv[sb], eff=er[sb], atr_z=atr_z[sb],
        tmin=d["tmin"][sb].astype(float),
        src_60m=(su.src.to_numpy() == "60m").astype(float),
        src_240m=(su.src.to_numpy() == "240m").astype(float),
        src_asia=(su.src.to_numpy() == "asia").astype(float),
        src_london=(su.src.to_numpy() == "london").astype(float),
        src_prevday=(su.src.to_numpy() == "prevday").astype(float)))
    return X


def control(R, k, draws=400, seed=7):
    rng = np.random.default_rng(seed)
    return np.array([R[rng.choice(len(R), size=k, replace=False)].mean() for _ in range(draws)])


if __name__ == "__main__":
    t0 = time.perf_counter()
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
        tr, info = E.run(d, su, atrs[B["atr_p"]][sb], entry=B["entry"], stop=B["stop"],
                         stop_k=B["stop_k"], stop_buf=0.25, tp="R", tp_r=B["tp_r"],
                         retest_bars=60)
        X = features(d, su, atrs[14]).iloc[:len(tr)].reset_index(drop=True)
        blk = splits(d["tday"], tr.fill_bar.to_numpy())
        m = blk["train"] & np.isfinite(X.to_numpy()).all(axis=1)
        R = tr.R.to_numpy()[m]
        Xt = X[m].reset_index(drop=True)
        hdr(f"{B['tag']}: {B['defn']} {B['tf']}m {B['entry']}/{B['stop']} atr{B['atr_p']} "
            f"k{B['stop_k']} tp{B['tp_r']}   TRAIN n={len(R)}  R/trade {R.mean():+.4f}")

        print("\n   BY SESSION / TIME OF DAY (tmin = minutes since the 18:00 roll)")
        buckets = [("Asia 18-03", 0, 540), ("London 03-08", 540, 840),
                   ("pre-NY 08-09:30", 840, 930), ("NY open 09:30-10", 930, 990),
                   ("NY 10-11:30", 990, 1080), ("NY lunch 11:30-13", 1080, 1140),
                   ("NY pm 13-16", 1140, 1320), ("after 16:00", 1320, 1440)]
        for nm, a_, b_ in buckets:
            sel = (Xt.tmin >= a_) & (Xt.tmin < b_)
            if sel.sum() >= 25:
                rr = R[sel.to_numpy()]
                pf = rr[rr > 0].sum() / abs(rr[rr < 0].sum()) if (rr < 0).any() else np.nan
                print(f"      {nm:<18} n {int(sel.sum()):>4}  R {rr.mean():>+8.4f}  PF {pf:>6.3f}"
                      f"  win {float((rr > 0).mean()):.3f}")

        print("\n   BY LIQUIDITY SOURCE")
        for s_ in ("60m", "240m", "asia", "london", "prevday"):
            sel = (Xt[f"src_{s_}"] == 1).to_numpy()
            if sel.sum() >= 25:
                rr = R[sel]
                pf = rr[rr > 0].sum() / abs(rr[rr < 0].sum()) if (rr < 0).any() else np.nan
                print(f"      {s_:<10} n {int(sel.sum()):>4}  R {rr.mean():>+8.4f}  PF {pf:>6.3f}")

        print("\n   SINGLE-FEATURE QUARTILES -- best quartile vs a same-size RANDOM subset")
        rows = []
        for col in Xt.columns:
            if col.startswith("src_") or col == "side":
                continue
            q = pd.qcut(Xt[col], 4, labels=False, duplicates="drop")
            if q.isna().all():
                continue
            best, bq = -9, None
            for i in range(int(np.nanmax(q)) + 1):
                sel = (q == i).to_numpy()
                if sel.sum() >= 25 and R[sel].mean() > best:
                    best, bq = R[sel].mean(), i
            if bq is None:
                continue
            sel = (q == bq).to_numpy()
            cc = control(R, int(sel.sum()))
            rows.append(dict(feature=col, quartile=bq, n=int(sel.sum()), R=best,
                             p=float((cc >= best).mean())))
        fr = pd.DataFrame(rows).sort_values("R", ascending=False)
        for r_ in fr.itertuples():
            flag = "  <-- clears the control" if r_.p <= 0.05 else ""
            print(f"      {r_.feature:<14} Q{r_.quartile}  n {r_.n:>4}  R {r_.R:>+8.4f}  "
                  f"control p {r_.p:.3f}{flag}")
        print(f"      features clearing p<=0.05: {int((fr.p <= 0.05).sum())} of {len(fr)}   "
              f"(expected by chance {0.05 * len(fr):.1f})")

        print("\n   GRADIENT-BOOSTED QUALITY SCORE, purged folds, with a shuffled twin")
        n = len(R)
        pred = np.full(n, np.nan); preds = np.full(n, np.nan)
        Rs = np.random.default_rng(3).permutation(R)
        edges = np.linspace(0, n, 7).astype(int)
        for f in range(6):
            te = np.zeros(n, bool); te[edges[f]:edges[f + 1]] = True
            trn = ~te
            for tgt, out in ((R, pred), (Rs, preds)):
                mdl = lgb.LGBMRegressor(n_estimators=200, num_leaves=7, learning_rate=0.03,
                                        subsample=0.8, subsample_freq=1, colsample_bytree=0.6,
                                        reg_lambda=5.0, min_child_samples=20, verbose=-1)
                mdl.fit(Xt[trn], tgt[trn])
                out[te] = mdl.predict(Xt[te])
        print(f"      {'keep':>6}{'n':>6}{'R/trade':>10}{'PF':>8}{'  ':>2}{'shuffled R':>12}"
              f"{'control p':>11}")
        for q in (1.0, 0.5, 0.25, 0.10):
            k = max(25, int(q * n))
            idx = np.argsort(-pred)[:k]
            rr = R[idx]
            js = np.argsort(-preds)[:k]
            pf = rr[rr > 0].sum() / abs(rr[rr < 0].sum()) if (rr < 0).any() else np.nan
            cc = control(R, k)
            print(f"      {q:>6.0%}{k:>6}{rr.mean():>+10.4f}{pf:>8.3f}{'  ':>2}"
                  f"{R[js].mean():>+12.4f}{float((cc >= rr.mean()).mean()):>11.3f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
