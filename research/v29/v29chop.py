"""Can a model PREDICT chop, and is an ATR regime filter worth tuning?

TWO QUESTIONS, DELIBERATELY SEPARATED.

1. PREDICTING CHOP. CHOP(14) is a CONTEMPORANEOUS measure -- it describes the last 14 bars, not the
   next ones. Gating on it is a bet that recent chop persists. The question a model can actually
   answer is different: can causal features forecast the FORWARD efficiency ratio, the straightness
   of the next h bars? And critically -- does a model's forecast of forward chop beat simply reading
   CURRENT CHOP? If it does not, the whole exercise reduces to the one-line filter already shipped.

2. ATR AS A REGIME FILTER, SWEPT. Volatility is the other regime axis, and V22 found the one thing
   on this branch that was not flat: heat measured in ATR units is 1.8-2.2x larger when realised vol
   sits LOW in its own percentile. Here ATR is tested as an ENTRY filter rather than a stop sizer,
   across four families and every parameter in a declared grid, each against a same-selectivity
   control.

THE BASELINE THAT MATTERS THROUGHOUT is not zero. It is the unfiltered breakout, and separately
CHOP <= 40, because a new regime filter has to beat the one already in the strategy.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v22")
sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v28")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v21regime as RG        # noqa: E402
import v22vol as VV           # noqa: E402
import v24ma as V             # noqa: E402
import v28data as D           # noqa: E402

import xgboost as xgb
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

# ---- the declared ATR regime grid ----
ATR_FAMILIES = {
    # ATR relative to its own trailing distribution: "is volatility high for this market lately"
    "atr_pct":   [("win", w, "thr", t) for w in (100, 250, 500) for t in (0.2, 0.35, 0.5, 0.65, 0.8)],
    # ATR expansion: ATR now against ATR n bars ago -- "is volatility RISING"
    "atr_exp":   [("lag", n, "thr", t) for n in (5, 10, 20, 50) for t in (0.9, 1.0, 1.1, 1.25, 1.5)],
    # ATR against its own moving average -- the classic normalisation
    "atr_ma":    [("win", w, "thr", t) for w in (20, 50, 100) for t in (0.8, 0.9, 1.0, 1.1, 1.25)],
    # ATR as a fraction of price -- comparable across instruments and price levels
    "atr_price": [("win", w, "thr", t) for w in (250, 500) for t in (0.2, 0.35, 0.5, 0.65, 0.8)],
}


def atr_feature(P, family, a, b):
    atr, c = P["atr"], P["c"]
    if family == "atr_pct":
        return pd.Series(atr).rolling(a, min_periods=a).rank(pct=True).to_numpy()
    if family == "atr_exp":
        return atr / np.maximum(I.shift(atr, a), 1e-12)
    if family == "atr_ma":
        return atr / np.maximum(I.sma(atr, a), 1e-12)
    if family == "atr_price":
        r = atr / np.maximum(c, 1e-12)
        return pd.Series(r).rolling(a, min_periods=a).rank(pct=True).to_numpy()
    raise ValueError(family)


def control_pf(O, pool, k, draws=300, seed=53):
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    out = np.empty(draws)
    for d in range(draws):
        m = np.zeros(n, bool)
        m[rng.choice(pool, size=k, replace=False)] = True
        idx = C.take(O, m)
        r = O["R"][idx]
        out[d] = r.mean() if len(idx) else np.nan
    return out[np.isfinite(out)]


def prep(market="NQ", tf=30):
    if market == "NQ":
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
    else:
        import v27run as R27
        b15 = R27.load_us30()
        df = pd.DataFrame(b15)
        df["blk"] = np.arange(len(df)) // (tf // 15)
        g = df.groupby("blk")
        b = dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(), h=g.h.max().to_numpy(),
                 l=g.l.min().to_numpy(), c=g.c.last().to_numpy(),
                 sess=g.sess.first().to_numpy(), mod=g["mod"].first().to_numpy())
        P = D.prep_bars(b, entry_n=30, exit_n=20, cost_mult=1.44)
    sig = C.signals(P, 1)
    O = C.outcomes(P, 1, sig, stop_mult=2.0, tp_r=0.0)
    return P, sig, O


def part1_predict_chop(market="NQ", tf=30, h=24):
    """Can XGBoost forecast forward chop better than simply reading CHOP now?"""
    P, sig, O = prep(market, tf)
    b = dict(o=P["o"], h=P["h"], l=P["l"], c=P["c"])
    er = VV.forward_er(P["c"], h)                 # 1.0 = straight line, ~0 = chop
    feats = {f"vol.{k}": v for k, v in VV.build(b["o"], b["h"], b["l"], b["c"]).items()}
    feats["chop14"] = RG.chop(P["h"], P["l"], P["c"], 14)
    feats["chop28"] = RG.chop(P["h"], P["l"], P["c"], 28)
    _p, _m, adx = I.adx_di(P["h"], P["l"], P["c"], 14)
    feats["adx14"] = adx
    X = pd.DataFrame(feats)
    ok = np.isfinite(X.to_numpy()).all(axis=1) & np.isfinite(er)
    X, y = X[ok].reset_index(drop=True), er[ok]
    sess = P["sess"][ok]
    u = np.unique(sess)
    cut = u[int(len(u) * 0.65)]
    res, lk = sess < cut, sess >= cut
    chop_now = X["chop14"].to_numpy()

    m = xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.03, subsample=0.8,
                         colsample_bytree=0.6, min_child_weight=50, reg_lambda=2.0,
                         random_state=0, n_jobs=-1, tree_method="hist")
    sc = StandardScaler().fit(X[res])
    m.fit(sc.transform(X[res]), y[res])
    pred = m.predict(sc.transform(X[lk]))
    # the naive baseline: LOW chop now => straight move next. Sign flipped so higher = trendier.
    naive = -chop_now[lk]
    return dict(market=market, h=h, n=int(lk.sum()),
                ic_model=float(spearmanr(pred, y[lk]).statistic),
                ic_naive=float(spearmanr(naive, y[lk]).statistic),
                ic_model_res=float(spearmanr(m.predict(sc.transform(X[res])), y[res]).statistic),
                auc_model=float(roc_auc_score((y[lk] > np.median(y[lk])).astype(int), pred)),
                auc_naive=float(roc_auc_score((y[lk] > np.median(y[lk])).astype(int), naive)))


def part2_atr_grid(market="NQ", tf=30):
    """Every declared ATR regime cell as an ENTRY filter, scored against a matched control."""
    P, sig, O = prep(market, tf)
    ch = RG.chop(P["h"], P["l"], P["c"], 14)[sig]
    res, lk = V.blocks(P["sess"])
    res, lk = res[sig], lk[sig]
    ok = O["xb"] >= 0
    rows = []
    for blkname, blk in (("research", res), ("locked", lk)):
        pool = np.flatnonzero(ok & blk)
        base = V.stat(P, O, ok & blk)
        cs = V.stat(P, O, ok & blk & np.isfinite(ch) & (ch <= 40))
        rows.append(dict(market=market, block=blkname, family="baseline", param="none",
                         n=base["n"], R=base["R"], pf=base["pf"], sharpe=base["sharpe"],
                         dd=base["dd"], excess=0.0, p=np.nan))
        rows.append(dict(market=market, block=blkname, family="CHOP<=40 (shipped)", param="14",
                         n=cs["n"], R=cs["R"], pf=cs["pf"], sharpe=cs["sharpe"], dd=cs["dd"],
                         excess=np.nan, p=np.nan))
        for fam, specs in ATR_FAMILIES.items():
            for (_k1, a, _k2, t) in specs:
                f = atr_feature(P, fam, a, t)[sig]
                for direction in (">=", "<="):
                    m = (f >= t) if direction == ">=" else (f <= t)
                    m &= np.isfinite(f)
                    keep = ok & m & blk
                    st = V.stat(P, O, keep)
                    if st is None:
                        continue
                    cp = control_pf(O, pool, int(keep.sum()))
                    rows.append(dict(market=market, block=blkname, family=fam,
                                     param=f"{a} {direction} {t:g}", n=st["n"], R=st["R"],
                                     pf=st["pf"], sharpe=st["sharpe"], dd=st["dd"],
                                     excess=st["R"] - cp.mean(),
                                     p=float((cp >= st["R"]).mean())))
    return pd.DataFrame(rows)
