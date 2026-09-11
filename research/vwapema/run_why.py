"""WHY DO THE TWO OPTUNA PRESETS HOLD OUT OF SAMPLE? Correlation matrices and a decomposition.

"Holds out of sample" has at least four explanations and only one of them is an edge:
  A. IT IS BETA. Gold rose ~167% over this sample. A rule that is long and loosely gated inherits
     that, and it will "hold" in every window where gold rose. Test: regress each preset's monthly
     result on GOLD'S OWN monthly return and read the beta and the R-squared.
  B. IT IS SAMPLE SIZE. The two that hold trade 2-3x more than the two that do not, so their fold
     estimates are simply less noisy and their gap shrinks toward zero for statistical reasons.
  C. IT IS SELECTIVITY. A preset whose conditions barely bind is closer to "be long in the New York
     session", which is a different thing from a signal.
  D. IT IS AN EDGE. Then it must beat ALWAYS-LONG on its own days, and its fold results must NOT be
     explained by the fold's gold return.

Everything below is a decomposition, not a new selection. No block is re-read.
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(2024)
pd.set_option("display.width", 235)
print(__doc__)
DS = {s: V.build(sess=s) for s in ("ny", "utc")}
SW = json.load(open("results/vwapema/sweep_cells.json"))
OP = json.load(open("results/vwapema/optuna_finalists.json"))
PRESETS = {
    "As published": dict(sess="ny", p=dict(V.PARAMS), tgt_R=3.0),
    "Optuna totR": {k: OP["totR"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Optuna PF": {k: OP["pf"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Optuna retDD": {k: OP["retdd"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Sweep top row": dict(sess=SW["top"]["sess"], p=SW["top"]["p"], tgt_R=SW["top"]["tgt_R"]),
    "Sweep nbhd": dict(sess=SW["robust"]["sess"], p=SW["robust"]["p"], tgt_R=SW["robust"]["tgt_R"]),
}


def trades(cfg):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=1, p=cfg["p"])
    t = V.run(D, sig, side=1, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
    t["m"] = pd.DatetimeIndex(t.ts).to_period("M")
    t["y"] = pd.DatetimeIndex(t.ts).year
    t["sig_n"] = int(sig.sum())
    return t


# gold's own monthly return, from the same bars
D0 = DS["ny"]
gp = pd.Series(D0["c"], index=pd.DatetimeIndex(D0["ix"])).resample("ME").last()
gold_m = np.log(gp).diff().dropna()
gold_m.index = gold_m.index.to_period("M")

TR = {k: trades(c) for k, c in PRESETS.items()}
MON = {k: t.groupby("m").R.sum() for k, t in TR.items()}
allm = gold_m.index
MM = pd.DataFrame({k: v.reindex(allm).fillna(0.0) for k, v in MON.items()})

print("=" * 120)
print("1. CORRELATION MATRIX -- the six presets' MONTHLY R against each other, and against GOLD")
print("=" * 120)
X = MM.copy(); X["GOLD (log ret)"] = gold_m
print(X.corr().round(3).to_string())
print("\n  The last row/column is the honest one: a strategy that is really long gold correlates")
print("  with gold. A signal that is not simply long correlates with it weakly.")

print("\n" + "=" * 120)
print("2. BETA TO GOLD -- regress each preset's monthly R on gold's monthly return")
print("=" * 120)
rows = []
for k in PRESETS:
    y = MM[k].to_numpy(); x = gold_m.to_numpy()
    m = np.isfinite(y) & np.isfinite(x)
    b, a = np.polyfit(x[m], y[m], 1)
    pred = a + b * x[m]
    r2 = 1 - np.sum((y[m] - pred) ** 2) / max(np.sum((y[m] - y[m].mean()) ** 2), 1e-12)
    # alpha in R per month, and the share of total R the beta term explains
    beta_R = float(b * x[m].sum())
    rows.append(dict(preset=k, beta=float(b), alpha_per_month=float(a), r2=float(r2),
                     total_R=float(y[m].sum()), R_from_beta=beta_R,
                     pct_from_gold=100 * beta_R / max(abs(y[m].sum()), 1e-9)))
B = pd.DataFrame(rows)
print(B.to_string(index=False, float_format=lambda v: f"{v:10.4f}"))
print("\n  `pct_from_gold` is the share of the whole result the gold-beta term accounts for.")

print("\n" + "=" * 120)
print("3. SELECTIVITY AND SAMPLE SIZE -- how much does each preset actually filter?")
print("=" * 120)
rth_n = int((D0["rth"] & np.isfinite(D0["vwap"])).sum())
rows = []
for k, c in PRESETS.items():
    t = TR[k]
    sg = int(t.sig_n.iloc[0]) if len(t) else 0
    yrs = (allm[-1] - allm[0]).n / 12
    rows.append(dict(preset=k, signals=sg, trades=len(t), trades_per_yr=len(t) / yrs,
                     pct_of_RTH_bars=100 * sg / rth_n,
                     locked_trades=int((t.blk == 1).sum()),
                     median_hold_bars=float((t.exit_bar - t.sig).median()),
                     win=100 * float((t.R > 0).mean())))
S = pd.DataFrame(rows)
print(S.to_string(index=False, float_format=lambda v: f"{v:10.3f}"))

print("\n" + "=" * 120)
print("4. THE DECISIVE TEST -- does each preset beat ALWAYS-LONG on its own days?")
print("=" * 120)
print("  Same days, same session, entered at the first bar of the session and exited at the same")
print("  clock the preset's trade ended on, one unit, same costs. If a preset does not beat this,")
print("  what it owns is the exposure and not the entry.\n")


def always_long(cfg, t):
    """Buy the first RTH bar of every day the preset traded, exit at that trade's exit bar."""
    D = DS[cfg["sess"]]
    o, c = D["o"], D["c"]
    day = D["day"]; rth = D["rth"]
    out = []
    for _, r in t.iterrows():
        d = day[int(r.sig)]
        idx = np.flatnonzero((day == d) & rth)
        if len(idx) == 0:
            continue
        ent = o[idx[0]] + V.SLIP
        ex = c[int(r.exit_bar)] - V.SLIP
        pts = ex - ent - V.COST_RT
        out.append(pts / max(r.risk, 1e-9))
    return np.array(out)


rows = []
for k, c in PRESETS.items():
    t = TR[k]
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        tt = t[t.blk == blk]
        if len(tt) < 20:
            continue
        al = always_long(c, tt)
        rows.append(dict(preset=k, block=bn, n=len(tt), rule_R=float(tt.R.mean()),
                         always_R=float(al.mean()), edge=float(tt.R.mean() - al.mean()),
                         beats=("yes" if tt.R.mean() > al.mean() else "NO")))
A = pd.DataFrame(rows)
print(A.to_string(index=False, float_format=lambda v: f"{v:10.4f}"))

print("\n" + "=" * 120)
print("5. FOLD-LEVEL -- does the fold's GOLD RETURN explain the fold's result?")
print("=" * 120)
W = 36
rows = []
for k in PRESETS:
    g = MM[k]
    fr, gr = [], []
    for s in range(0, len(allm) - W - 12 + 1, 12):
        te = slice(s + W, s + W + 12)
        fr.append(float(g.iloc[te].sum())); gr.append(float(gold_m.iloc[te].sum()))
    fr, gr = np.array(fr), np.array(gr)
    rows.append(dict(preset=k, folds=len(fr), corr_fold_R_vs_gold=float(np.corrcoef(fr, gr)[0, 1]),
                     folds_pos=int((fr > 0).sum()),
                     folds_pos_when_gold_up=int(((fr > 0) & (gr > 0)).sum()),
                     folds_gold_up=int((gr > 0).sum()),
                     mean_R_gold_up=float(fr[gr > 0].mean()) if (gr > 0).any() else np.nan,
                     mean_R_gold_down=float(fr[gr <= 0].mean()) if (gr <= 0).any() else np.nan))
F = pd.DataFrame(rows)
print(F.to_string(index=False, float_format=lambda v: f"{v:10.3f}"))
print("\n  If `mean_R_gold_up` is strongly positive and `mean_R_gold_down` is not, the preset is a")
print("  conditional long, and 'holding out of sample' means 'gold kept rising in those folds'.")

MM.to_csv("results/vwapema/why_monthly.csv")
X.corr().to_csv("results/vwapema/why_corr.csv")
B.to_csv("results/vwapema/why_beta.csv", index=False)
S.to_csv("results/vwapema/why_selectivity.csv", index=False)
A.to_csv("results/vwapema/why_alwayslong.csv", index=False)
F.to_csv("results/vwapema/why_folds.csv", index=False)
