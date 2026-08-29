"""Read the optimiser's own surface: does it transfer, and can a booster learn it?

FOUR QUESTIONS, IN THE ORDER THAT DECIDES WHETHER THE LATER ONES MATTER.

  A. THE POPULATION, before any ranking. What share of trials is profitable at all? A grid where
     most cells make money is a grid where the top cell is the maximum of many profitable draws --
     which is drift, not selection skill (STUDY_V14_WINDOW_GRID).
  B. TRANSFER. The correlation between a trial's RESEARCH Sharpe and its LOCKED Sharpe. If that is
     near zero, the optimiser's ranking is a description of one block.
  C. THE SURROGATE. XGBoost and LightGBM trained on (parameters -> research Sharpe), then asked to
     predict LOCKED Sharpe on held-out trials. A booster that cannot learn the map is direct
     evidence the map does not exist -- and it is a stronger test than a correlation, because it
     can find non-linear structure a correlation misses.
  D. THE WINNER, read once, against a same-selectivity control and against the un-optimised
     starting point. A search is only worth its multiplicity if it beats not searching.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")
sys.path.insert(0, "research"); sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v27"); sys.path.insert(0, "research/v30")
import v30opt as O            # noqa: E402
import xgboost as xgb         # noqa: E402
import lightgbm as lgb        # noqa: E402
from sklearn.model_selection import KFold   # noqa: E402

PARAMS = ["entry1", "exit1", "atr_len", "atr_mult", "pyr_step", "max_units",
          "adx_max", "ext_max", "ao_min", "skip_win"]
COST = {"NQ": 1.72, "US30": 2.50}


def hdr(t):
    print("\n" + "=" * 112 + f"\n{t}\n" + "=" * 112)


def surrogate(X, y, name):
    """Out-of-fold prediction, so the surrogate is never scored on what it fitted."""
    kf = KFold(5, shuffle=True, random_state=0)
    pred = np.empty(len(y))
    for tr, te in kf.split(X):
        m = (xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8,
                              colsample_bytree=0.7, min_child_weight=10, random_state=0,
                              n_jobs=-1, tree_method="hist") if name == "XGBoost"
             else lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=15,
                                    min_child_samples=20, subsample=0.8, colsample_bytree=0.7,
                                    random_state=0, verbose=-1))
        m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return pred


if __name__ == "__main__":
    d = pd.read_csv("results/v30/v30_trials.csv")
    d["skip_win"] = d.skip_win.astype(int)
    hdr("A. THE POPULATION -- what the optimiser was searching, before any ranking")
    print(f"   {len(d)} scorable trials across 2 markets x 2 sides, 07:00-11:00 New York,"
          f" flatten at 11:00\n")
    print(f"   {'market':<8}{'side':<7}{'trials':>8}{'res Sh>0':>10}{'res PF>1':>10}"
          f"{'LOCK Sh>0':>11}{'LOCK PF>1':>11}{'best res Sh':>13}{'its LOCK Sh':>13}")
    for (mkt, side), g in d.groupby(["market", "side"]):
        v = g.dropna(subset=["lk_sharpe"])
        b = g.loc[g.res_sharpe.idxmax()]
        print(f"   {mkt:<8}{side:<7}{len(g):>8}{(g.res_sharpe>0).mean():>10.0%}"
              f"{(g.res_pf>1).mean():>10.0%}{(v.lk_sharpe>0).mean():>11.0%}"
              f"{(v.lk_pf>1).mean():>11.0%}{b.res_sharpe:>+13.3f}{b.lk_sharpe:>+13.3f}")

    hdr("B. TRANSFER -- does a trial's research score say anything about its locked score?")
    print(f"   {'market':<8}{'side':<7}{'n':>7}{'Pearson':>10}{'Spearman':>11}"
          f"{'top-10% res -> mean LOCK Sh':>30}{'all-trial mean LOCK Sh':>25}")
    for (mkt, side), g in d.groupby(["market", "side"]):
        v = g.dropna(subset=["lk_sharpe"])
        if len(v) < 30:
            continue
        top = v.nlargest(max(5, len(v) // 10), "res_sharpe")
        print(f"   {mkt:<8}{side:<7}{len(v):>7}{np.corrcoef(v.res_sharpe, v.lk_sharpe)[0,1]:>+10.3f}"
              f"{spearmanr(v.res_sharpe, v.lk_sharpe).statistic:>+11.3f}"
              f"{top.lk_sharpe.mean():>+30.3f}{v.lk_sharpe.mean():>+25.3f}")

    hdr("C. THE SURROGATE -- can a booster learn the parameter surface, and does it transfer?")
    print("   Trained on (parameters -> RESEARCH Sharpe), out-of-fold. Then the SAME model's")
    print("   predictions are correlated against the LOCKED Sharpe. Learning research and failing")
    print("   locked is the signature of a surface that exists in one block only.\n")
    print(f"   {'market':<8}{'side':<7}{'model':<11}{'fits research':>16}{'predicts LOCKED':>18}")
    for (mkt, side), g in d.groupby(["market", "side"]):
        v = g.dropna(subset=["lk_sharpe"])
        if len(v) < 60:
            continue
        X = v[PARAMS].to_numpy(float)
        for name in ("XGBoost", "LightGBM"):
            p = surrogate(X, v.res_sharpe.to_numpy(), name)
            print(f"   {mkt:<8}{side:<7}{name:<11}"
                  f"{spearmanr(p, v.res_sharpe).statistic:>+16.3f}"
                  f"{spearmanr(p, v.lk_sharpe).statistic:>+18.3f}")


def part_d():
    """The winner, read once, against the un-optimised starting point and a matched control."""
    d = pd.read_csv("results/v30/v30_trials.csv")
    hdr("D. THE WINNER -- one locked read, against not searching at all")
    print("   `spec` is the Turtle's own defaults in this window, with no search: entry 20,")
    print("   exit 10, ATR 20, 2.0N, 0.5N ladder to 4 units, no gates. `best` is the top trial of")
    print("   400 by research Sharpe. `robust` is the trial with the best MEAN Sharpe over its own")
    print("   neighbourhood -- the 20 nearest trials in normalised parameter space.\n")
    spec = dict(entry1=20, exit1=10, atr_len=20, atr_mult=2.0, pyr_step=0.5, max_units=4,
                adx_max=0.0, ext_max=0.0, ao_min=-999.0, skip_win=True)
    print(f"   {'market':<7}{'side':<7}{'config':<9}{'RESEARCH':>26}{'|':>3}{'LOCKED':>26}")
    print(f"   {'':<7}{'':<7}{'':<9}{'n':>6}{'Sharpe':>9}{'PF':>8}{'|':>3}"
          f"{'n':>6}{'Sharpe':>9}{'PF':>8}{'R/trade':>9}")
    for mkt in ("NQ", "US30"):
        b = O.load(mkt, 30)
        u = np.unique(b["sess"]); cut = u[int(len(u) * 0.65)]
        res, lk = b["sess"] < cut, b["sess"] >= cut
        for side_s, side in (("long", 1), ("short", -1)):
            g = d[(d.market == mkt) & (d.side == side_s)].copy()
            if not len(g):
                continue
            # neighbourhood mean, on normalised parameters
            P = g[PARAMS].to_numpy(float)
            Z = (P - P.mean(0)) / np.maximum(P.std(0), 1e-9)
            nbr = np.empty(len(g))
            for i in range(len(g)):
                dist = np.sqrt(((Z - Z[i]) ** 2).sum(1))
                nbr[i] = g.res_sharpe.to_numpy()[np.argsort(dist)[:20]].mean()
            g["nbr"] = nbr
            cfgs = [("spec", spec),
                    ("best", {k: g.loc[g.res_sharpe.idxmax(), k] for k in PARAMS}),
                    ("robust", {k: g.loc[g.nbr.idxmax(), k] for k in PARAMS})]
            for name, p in cfgs:
                p = {k: (bool(v) if k == "skip_win" else
                         (int(v) if k in ("entry1", "exit1", "atr_len", "max_units") else float(v)))
                     for k, v in p.items()}
                r = O.score(b, p, side, res, COST[mkt])
                l = O.score(b, p, side, lk, COST[mkt])
                line = f"   {mkt:<7}{side_s:<7}{name:<9}"
                for s in (r, l):
                    if s is None:
                        line += f"{'-- under 25 trades':>26}" if s is l else f"{'--':>6}{'':>9}{'':>8}"
                    elif s is r:
                        line += f"{s['n']:>6}{s['sharpe']:>+9.3f}{s['pf']:>8.3f}"
                    else:
                        line += f"{s['n']:>6}{s['sharpe']:>+9.3f}{s['pf']:>8.3f}{s['R']:>+9.4f}"
                    if s is r:
                        line += f"{'|':>3}"
                print(line)
    print("\n   A search is only worth its multiplicity if `best` beats `spec` OUT OF SAMPLE.")


if __name__ == "__main__":
    part_d()
