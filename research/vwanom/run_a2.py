"""A2 -- the model ladder, every model beside a SHUFFLED TWIN, then GATE 2 on unsized returns.

FOUR THINGS THIS FILE DOES THAT AN ORDINARY FEATURE STUDY DOES NOT:
  * PURGED AND EMBARGOED folds. An event occupies [signal bar, exit bar] and neighbouring events
    share future bars, so an ordinary K-fold trains on the answer. `label_horizon` is the median
    hold in events, and 1% of the sample is embargoed either side.
  * A SHUFFLED TWIN for every model. On this branch the shuffled label beat the real model in 83 of
    120 research cells once (`STUDY_V32_FLOW_ML`); above 50% means the noise floor is higher than
    the signal, and no other diagnostic shows it.
  * THE OBJECTIVE IS THE RETURN, NOT WIN/LOSE. A win/lose objective is a win-rate optimiser, and a
    trend system earns in the tail: `STUDY_V28` and `STUDY_V32` both measured p90 of R FALLING in
    the kept set when trained on win, and rising when trained on R. p90 is printed for every cell.
  * EVERY CANDIDATE'S RETURN STREAM IS KEPT, including the ones that lose, because White's reality
    check needs the whole set and not the survivor.
"""
import os, sys, time, pickle
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, SK + "/mechanism-first-alpha/scripts")
sys.path.insert(0, SK + "/quant-strategy-lab/scripts")
import gates, splits

RNG = np.random.default_rng(17)
pd.set_option("display.width", 230)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)
BUNDLE = pickle.load(open("results/vwanom/feat_cache.pkl", "rb"))
FCOLS = list(BUNDLE[("US30", "LONG")]["feat"].columns)
PRIMARIES = [("US100", "SHORT"), ("US30", "LONG")]      # each cell on the market that chose it
KEEPS = (0.3, 0.5, 0.7)
CAND = {}                                                # every candidate's kept-return stream
SCORES = {}                                              # every model's OOF score vector


def prep(mk, sd, blk):
    b = BUNDLE[(mk, sd)]
    m, X = b["meta"], b["feat"]
    sel = m.blk == blk if blk is not None else np.ones(len(m), bool)
    Xs = X.loc[sel.values, FCOLS].to_numpy(float)
    mu = np.nanmedian(Xs, 0)
    Xs = np.where(np.isfinite(Xs), Xs, mu)
    y = m.loc[sel.values, "pct"].to_numpy() / 100.0
    hold = (m.loc[sel.values, "exit_bar"] - m.loc[sel.values, "sig"]).to_numpy()
    return Xs, y, m.loc[sel.values].reset_index(drop=True), int(np.median(hold))


def models(seed=0):
    from sklearn.linear_model import RidgeCV
    from sklearn.ensemble import RandomForestRegressor
    import lightgbm as lgb, xgboost as xgb
    return {
        "ridge": lambda: RidgeCV(alphas=np.logspace(-2, 3, 12)),
        "rf (regularised)": lambda: RandomForestRegressor(
            n_estimators=300, max_depth=4, min_samples_leaf=40, max_features=0.4,
            random_state=seed, n_jobs=2),
        "lightgbm d3": lambda: lgb.LGBMRegressor(
            n_estimators=250, max_depth=3, num_leaves=7, learning_rate=0.03,
            min_child_samples=40, subsample=0.8, colsample_bytree=0.6,
            random_state=seed, verbose=-1, n_jobs=2),
        "xgboost d3": lambda: xgb.XGBRegressor(
            n_estimators=250, max_depth=3, learning_rate=0.03, min_child_weight=20,
            subsample=0.8, colsample_bytree=0.6, random_state=seed, n_jobs=2, verbosity=0),
        "xgboost d6": lambda: xgb.XGBRegressor(
            n_estimators=250, max_depth=6, learning_rate=0.03, min_child_weight=10,
            subsample=0.8, colsample_bytree=0.6, random_state=seed, n_jobs=2, verbosity=0),
    }


class MLP:
    """Deep arm. Torch is pinned to two threads and the arms run SEQUENTIALLY -- two torch
    processes on four cores oversubscribe and ran 31 minutes without producing a row that one
    process produces in twelve (`STUDY_EMA48_VWAP_DL`)."""

    def __init__(self, hidden=(64, 64), epochs=120, seed=0):
        self.hidden, self.epochs, self.seed = hidden, epochs, seed

    def fit(self, X, y):
        import torch
        torch.manual_seed(self.seed)
        torch.set_num_threads(2)
        self.mu_, self.sd_ = X.mean(0), X.std(0) + 1e-9
        Z = torch.tensor((X - self.mu_) / self.sd_, dtype=torch.float32)
        Y = torch.tensor(y.reshape(-1, 1) / (y.std() + 1e-12), dtype=torch.float32)
        layers, d = [], X.shape[1]
        for h in self.hidden:
            layers += [torch.nn.Linear(d, h), torch.nn.ReLU(), torch.nn.Dropout(0.1)]
            d = h
        layers += [torch.nn.Linear(d, 1)]
        self.net = torch.nn.Sequential(*layers)
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3, weight_decay=1e-4)
        for _ in range(self.epochs):
            perm = torch.randperm(len(Z))
            for i in range(0, len(Z), 256):
                b = perm[i:i + 256]
                opt.zero_grad()
                loss = ((self.net(Z[b]) - Y[b]) ** 2).mean()
                loss.backward()
                opt.step()
        return self

    def predict(self, X):
        import torch
        Z = torch.tensor((X - self.mu_) / self.sd_, dtype=torch.float32)
        with torch.no_grad():
            return self.net(Z).numpy().ravel()


def oof(make, X, y, hold, n_splits=6, shuffle_y=False, seed=0):
    """Out-of-fold predictions under purged, embargoed folds."""
    yy = np.random.default_rng(seed).permutation(y) if shuffle_y else y
    pred = np.full(len(y), np.nan)
    for tr, te in splits.purged_kfold(len(y), n_splits=n_splits, label_horizon=hold, embargo_pct=0.01):
        if len(tr) < 80 or len(te) < 10:
            continue
        mdl = make()
        mdl.fit(X[tr], yy[tr])
        pred[te] = mdl.predict(X[te])
    return pred


L("A2.1  THE LADDER -- research block only, every model beside its shuffled twin")
rows = []
t0 = time.time()
for mk, sd in PRIMARIES:
    X, y, meta, hold = prep(mk, sd, 0)
    base = y.mean()
    print(f"\n  --- {mk} {sd}: {len(y)} research events, median hold {hold} bars, "
          f"base {1e2*base:+.4f} % of price")
    arms = list(models().items()) + [("mlp 2x64", lambda: MLP((64, 64), seed=0)),
                                     ("mlp 4x128", lambda: MLP((128, 128, 128, 128), seed=0))]
    for nm, make in arms:
        for shuf in (False, True):
            p = oof(make, X, y, hold, shuffle_y=shuf, seed=3)
            ok = np.isfinite(p)
            ic = float(pd.Series(p[ok]).corr(pd.Series(y[ok]), method="spearman"))
            row = dict(feed=mk, cell=sd, model=nm, shuffled=shuf, ic=round(ic, 4))
            for k in KEEPS:
                thr = np.nanquantile(p, 1 - k)
                keep = ok & (p >= thr)
                r = y[keep]
                row[f"keep{int(k*100)}"] = round(1e2 * r.mean(), 4)
                row[f"p90_{int(k*100)}"] = round(1e2 * np.percentile(r, 90), 3)
                if not shuf:
                    CAND[(mk, sd, nm, k)] = r
            if not shuf:
                SCORES[(mk, sd, nm)] = p
            rows.append(row)
        print(f"    {nm:18s} real IC {rows[-2]['ic']:+.4f}  shuffled {rows[-1]['ic']:+.4f}  "
              f"keep50 {rows[-2]['keep50']:+.4f} vs {rows[-1]['keep50']:+.4f}  ({time.time()-t0:.0f}s)")
A = pd.DataFrame(rows)
A.to_csv("results/vwanom/a2_ladder.csv", index=False)
pickle.dump(CAND, open("results/vwanom/a2_candidates.pkl", "wb"))
pickle.dump(SCORES, open("results/vwanom/a2_scores.pkl", "wb"))

L("A2.2  DOES THE SHUFFLED TWIN OUTSCORE THE REAL MODEL?")
p = A.pivot_table(index=["feed", "cell", "model"], columns="shuffled",
                  values=["ic", "keep30", "keep50", "keep70"])
beat = {}
for col in ("ic", "keep30", "keep50", "keep70"):
    beat[col] = float((p[(col, True)] > p[(col, False)]).mean())
print("  share of cells where the SHUFFLED twin beats the real model (0.50 = the noise floor):")
print("   " + "   ".join(f"{k} {v:.2f}" for k, v in beat.items()))
print("\n" + p.round(4).to_string())

L("A2.3  GATE 2 -- the meta layer's uplift on UNSIZED returns, research block")
rows = []
SCORES = pickle.load(open("results/vwanom/a2_scores.pkl", "rb"))
for (mk, sd, nm, k), r in CAND.items():
    X, y, meta, hold = prep(mk, sd, 0)
    p = SCORES[(mk, sd, nm)]
    thr = float(np.nanquantile(p, 1 - k))
    g = gates.meta_gate(y, np.nan_to_num(p, nan=-1e18), thr)
    rows.append(dict(feed=mk, cell=sd, model=nm, keep=k, n_kept=int(g["n_kept"]),
                     kept_frac=round(float(g["kept_fraction"]), 3),
                     base=round(1e2 * float(g["unsized_mean_unfiltered"]), 4),
                     kept=round(1e2 * float(g["unsized_mean_filtered"]), 4),
                     uplift=round(1e2 * float(g["unsized_uplift"]), 4),
                     ci_lo=round(1e2 * float(g["unsized_uplift_ci95"][0]), 4),
                     ci_hi=round(1e2 * float(g["unsized_uplift_ci95"][1]), 4),
                     boot_p=round(float(g["bootstrap_p_one_sided"]), 3),
                     hit_base=round(float(g["hit_rate_unfiltered"]), 3),
                     hit_kept=round(float(g["hit_rate_filtered"]), 3),
                     p90_base=round(1e2 * np.percentile(y, 90), 3),
                     p90_kept=round(1e2 * np.percentile(r, 90), 3),
                     verdict=str(g["verdict"])[:34]))
G = pd.DataFrame(rows).sort_values("uplift", ascending=False)
print(G.to_string(index=False))
G.to_csv("results/vwanom/a2_gate2.csv", index=False)
print(f"\n  candidates evaluated and KEPT for the reality check: {len(CAND)}")
