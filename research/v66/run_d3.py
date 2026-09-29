"""D3 -- the model ladder, the shuffled twin, the FAMILY ABLATION, and Gate 2.

THE LADDER runs ridge -> regularised random forest -> LightGBM -> XGBoost d3 -> XGBoost d6 ->
MLP 2x32 -> MLP 2x64 -> MLP 4x128, so capacity is an axis rather than an assumption. This branch
has measured capacity three ways and got three answers -- monotonically harmful (V28), inert (S3),
and linear-wins (V48, EMA48) -- so it is swept, not chosen.

FOUR THINGS THAT ARE NOT OPTIONAL HERE:
  * PURGED + EMBARGOED folds. An event occupies [signal, exit] and those windows OVERLAP, so a
    naive split trains on the answer.
  * UNIQUENESS WEIGHTS, for the same reason: concurrent events are not independent observations.
  * A SHUFFLED-LABEL TWIN beside every model. STUDY_V28's deepest net's shuffled twin outscored
    every real model on the headline statistic; STUDY_VWANOM's twins won 71% of cells. Above 50%
    the noise floor is higher than the signal, and that is the finding rather than a footnote.
  * THE OBJECTIVE IS THE RETURN, NOT WIN/LOSE. Trained on win/lose the models raise the win rate
    and cut p90 of R in all four market-block cells (STUDY_V32) -- a breakout earns in the tail, so
    a win-rate objective is misaligned with the thing being maximised. p90 of R is printed for
    every cell.

Torch is pinned to one thread: two torch processes on four cores oversubscribe and a ladder that
takes twelve minutes sequentially took thirty-one and produced nothing (recorded in CLAUDE.md).
"""
import os, pickle, sys, time, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import deflated_sharpe, effective_trials, reality_check     # noqa: E402
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb, xgboost as xgb
import torch, torch.nn as nn
torch.set_num_threads(1)

t0 = time.time()
pd.set_option("display.width", 220)
print(__doc__)
FE = pd.read_parquet("results/v66/events_features.parquet")
with open("results/v66/frozen.pkl", "rb") as f:
    Z = pickle.load(f)
COLS, FAM = Z["cols"], Z["fam"]
R = FE[FE.blk == 0].reset_index(drop=True)
L = FE[FE.blk == 1].reset_index(drop=True)
rng = np.random.default_rng(66)

def line(t):
    print("\n" + "=" * 126); print(t); print("=" * 126, flush=True)

# ---- uniqueness weights: an event overlapping many others is not a full observation
def uniqueness(df):
    s = df.day.to_numpy().astype(float)
    w = np.ones(len(df))
    for i in range(len(df)):
        w[i] = 1.0 / max(1.0, np.sum(np.abs(s - s[i]) < 1e-9))
    return w / w.mean()

def purged_folds(n, k=5, embargo=0.02):
    edges = np.linspace(0, n, k + 1).astype(int)
    emb = int(np.ceil(embargo * n))
    for j in range(k):
        te = np.arange(edges[j], edges[j + 1])
        tr = np.concatenate([np.arange(0, max(0, edges[j] - emb)),
                             np.arange(min(n, edges[j + 1] + emb), n)])
        yield tr, te

class MLP(nn.Module):
    def __init__(self, p, hid, depth):
        super().__init__()
        layers, d = [], p
        for _ in range(depth):
            layers += [nn.Linear(d, hid), nn.ReLU(), nn.Dropout(0.15)]
            d = hid
        layers += [nn.Linear(d, 1)]
        self.f = nn.Sequential(*layers)
    def forward(self, x):
        return self.f(x).squeeze(-1)

def fit_torch(Xtr, ytr, wtr, Xte, hid, depth, seed=0, epochs=220):
    torch.manual_seed(seed)
    m = MLP(Xtr.shape[1], hid, depth)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3, weight_decay=1e-3)
    xt = torch.tensor(Xtr, dtype=torch.float32); yt = torch.tensor(ytr, dtype=torch.float32)
    wt = torch.tensor(wtr, dtype=torch.float32)
    for _ in range(epochs):
        opt.zero_grad()
        loss = (wt * (m(xt) - yt) ** 2).mean()
        loss.backward(); opt.step()
    m.eval()
    with torch.no_grad():
        return m(torch.tensor(Xte, dtype=torch.float32)).numpy()

MODELS = ["ridge", "rf", "lgbm", "xgb_d3", "xgb_d6", "mlp_2x32", "mlp_2x64", "mlp_4x128"]

def fit_predict(kind, Xtr, ytr, wtr, Xte, seed=0):
    if kind == "ridge":
        m = Ridge(alpha=5.0); m.fit(Xtr, ytr, sample_weight=wtr); return m.predict(Xte)
    if kind == "rf":
        m = RandomForestRegressor(n_estimators=400, max_depth=4, min_samples_leaf=25,
                                  max_features=0.5, random_state=seed, n_jobs=2)
        m.fit(Xtr, ytr, sample_weight=wtr); return m.predict(Xte)
    if kind == "lgbm":
        m = lgb.LGBMRegressor(n_estimators=250, learning_rate=0.03, num_leaves=7, max_depth=3,
                              min_child_samples=30, subsample=0.8, colsample_bytree=0.6,
                              reg_lambda=5.0, random_state=seed, verbose=-1)
        m.fit(Xtr, ytr, sample_weight=wtr); return m.predict(Xte)
    if kind.startswith("xgb"):
        d = 3 if kind.endswith("d3") else 6
        m = xgb.XGBRegressor(n_estimators=300, learning_rate=0.03, max_depth=d,
                             min_child_weight=10, subsample=0.8, colsample_bytree=0.6,
                             reg_lambda=5.0, random_state=seed, n_jobs=2, verbosity=0)
        m.fit(Xtr, ytr, sample_weight=wtr); return m.predict(Xte)
    hid, depth = {"mlp_2x32": (32, 2), "mlp_2x64": (64, 2), "mlp_4x128": (128, 4)}[kind]
    return fit_torch(Xtr, ytr, wtr, Xte, hid, depth, seed=seed)

def oof(df, cols, kind, seed=0, shuffle=False):
    X = df[cols].to_numpy(float); y = df.R.to_numpy(float); w = uniqueness(df)
    sc = StandardScaler().fit(X); X = sc.transform(X)
    if shuffle:
        y = y.copy(); rng.shuffle(y)
    p = np.full(len(df), np.nan)
    for tr, te in purged_folds(len(df)):
        if len(tr) < 60:
            continue
        p[te] = fit_predict(kind, X[tr], y[tr], w[tr], X[te], seed=seed)
    return p

def ic(p, y):
    m = np.isfinite(p) & np.isfinite(y)
    if m.sum() < 20:
        return np.nan
    return float(pd.Series(p[m]).corr(pd.Series(y[m]), method="spearman"))

line("D3.1  THE LADDER -- out-of-fold IC on the RETURN, each model beside its shuffled twin")
print(f"  research events {len(R)}   features {len(COLS)}   folds 5 purged + 2% embargo")
print(f"\n{'model':>10} {'IC real':>9} {'IC shuf':>9} {'twin wins':>10} {'PF@keep60':>10} "
      f"{'p90 R':>8} {'base p90':>9}")
y = R.R.to_numpy(float)
base_pf = y[y > 0].sum() / max(-y[y < 0].sum(), 1e-9)
base_p90 = float(np.quantile(y, 0.90))
rowsL, preds = [], {}
for k in MODELS:
    pr = oof(R, COLS, k, seed=1)
    ps = oof(R, COLS, k, seed=1, shuffle=True)
    preds[k] = pr
    i_r, i_s = ic(pr, y), ic(ps, y)
    thr = np.nanquantile(pr, 0.40)
    sel = y[np.isfinite(pr) & (pr >= thr)]
    pf = sel[sel > 0].sum() / max(-sel[sel < 0].sum(), 1e-9) if len(sel) > 10 else np.nan
    p90 = float(np.quantile(sel, 0.90)) if len(sel) > 10 else np.nan
    rowsL.append(dict(model=k, ic=i_r, ic_shuf=i_s, pf=pf, p90=p90))
    print(f"{k:>10} {i_r:>9.4f} {i_s:>9.4f} {str(i_s > i_r):>10} {pf:>10.3f} {p90:>8.3f} "
          f"{base_p90:>9.3f}", flush=True)
LD = pd.DataFrame(rowsL)
nw = int((LD.ic_shuf > LD.ic).sum())
print(f"\n  base: PF {base_pf:.3f}  p90 of R {base_p90:.3f}  mean R {y.mean():+.4f}")
print(f"  SHUFFLED TWIN BEATS THE REAL MODEL IN {nw} OF {len(LD)} CELLS "
      f"({100*nw/len(LD):.0f}%) -- above 50% the noise floor is higher than the signal")
print(f"  capacity: ridge {LD.ic.iloc[0]:+.4f} -> mlp_4x128 {LD.ic.iloc[-1]:+.4f}")

line("D3.2  FAMILY ABLATION -- does the PIN family earn a place after failing as a primary?")
best = LD.sort_values("ic", ascending=False).model.iloc[0]
print(f"  model = {best} (best OOF IC in the ladder)\n")
print(f"{'feature set':>26} {'k':>4} {'IC':>9} {'d vs all':>9} {'PF@60':>8} {'p90 R':>8}")
def score(cols, tag):
    pr = oof(R, cols, best, seed=1)
    i_ = ic(pr, y)
    thr = np.nanquantile(pr, 0.40)
    sel = y[np.isfinite(pr) & (pr >= thr)]
    pf = sel[sel > 0].sum() / max(-sel[sel < 0].sum(), 1e-9) if len(sel) > 10 else np.nan
    p90 = float(np.quantile(sel, 0.90)) if len(sel) > 10 else np.nan
    return i_, pf, p90
ic_all, pf_all, p90_all = score(COLS, "all")
print(f"{'ALL':>26} {len(COLS):>4} {ic_all:>9.4f} {0.0:>9.4f} {pf_all:>8.3f} {p90_all:>8.3f}")
abl = []
for fam in FAM:
    keep = [c for c in COLS if not c.startswith(fam + ".")]
    i_, pf, p90 = score(keep, fam)
    abl.append(dict(dropped=fam, k=len(keep), ic=i_, d=i_ - ic_all, pf=pf, p90=p90))
    print(f"{'drop ' + fam:>26} {len(keep):>4} {i_:>9.4f} {i_-ic_all:>+9.4f} {pf:>8.3f} "
          f"{p90:>8.3f}", flush=True)
pin_only = [c for c in COLS if c.startswith("pin.")]
i_, pf, p90 = score(pin_only, "pin only")
abl.append(dict(dropped="PIN ONLY", k=len(pin_only), ic=i_, d=i_ - ic_all, pf=pf, p90=p90))
print(f"{'PIN family alone':>26} {len(pin_only):>4} {i_:>9.4f} {i_-ic_all:>+9.4f} {pf:>8.3f} "
      f"{p90:>8.3f}")
i_, pf, p90 = score(["pin.imb"], "imb only")
print(f"{'pin.imb alone (control)':>26} {1:>4} {i_:>9.4f} {i_-ic_all:>+9.4f} {pf:>8.3f} "
      f"{p90:>8.3f}")
AB = pd.DataFrame(abl)
AB.to_csv("results/v66/d3_ablation.csv", index=False)
LD.to_csv("results/v66/d3_ladder.csv", index=False)
np.save("results/v66/d3_preds.npy", np.array([preds[k] for k in MODELS]))
print(f"\n[{time.time()-t0:.0f}s]")
