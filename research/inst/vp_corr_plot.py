"""Correlation matrix of the 45 VP/TPO/EMA/ATR features on the base's research SIGNAL BARS (a filter
only ever acts on the bars the trigger fires on -- STUDY_V40), Spearman, ordered by family and then
by hierarchical clustering; plus the |rho| >= 0.9 pairs, which are the near-duplicates."""
import os, sys, warnings, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import linkage, leaves_list
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v64opt as O, vp_tpo as T
warnings.filterwarnings("ignore"); OUT = os.path.join(ROOT, "results/inst")
D = O.build(15); n = D["n"]; CUT = D["cut"]; h, mod = D["h"], D["mod"]
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]
F, L = T.build(D)
sig = np.zeros(n, bool); sig[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]; sig &= np.arange(n) < CUT
X = F[sig]; X = X.loc[:, X.notna().mean() >= 0.25]        # features present on at least a quarter of the signal bars
C = X.corr(method="spearman", min_periods=100)
fam_order = ["vp", "tpo", "ema", "atr"]; cols = sorted(C.columns, key=lambda k: (fam_order.index(k.split(".")[0]), k)); C = C.loc[cols, cols]
BG = "#0f1115"; FG = "#e6e6e6"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "text.color": FG, "xtick.color": FG, "ytick.color": FG, "axes.edgecolor": "#2a2e36"})
def heat(ax, M, title):
    im = ax.imshow(M.values, cmap="RdBu_r", vmin=-1, vmax=1, interpolation="nearest")
    ax.set_xticks(range(len(M))); ax.set_yticks(range(len(M))); ax.set_xticklabels(M.columns, rotation=90, fontsize=6.5); ax.set_yticklabels(M.index, fontsize=6.5); ax.set_title(title, fontsize=11)
    # family separators
    fams = [k.split(".")[0] for k in M.columns]
    for i in range(1, len(fams)):
        if fams[i] != fams[i - 1]: ax.axhline(i - 0.5, color=FG, lw=0.8); ax.axvline(i - 0.5, color=FG, lw=0.8)
    return im
fig, axs = plt.subplots(1, 2, figsize=(22, 11))
im = heat(axs[0], C, f"Spearman correlation on {int(sig.sum()):,} research signal bars, ordered by family (vp | tpo | ema | atr)")
# clustered order
Z = linkage(C.fillna(0).values, method="average", metric="correlation"); order = leaves_list(Z); Cc = C.iloc[order, order]
heat(axs[1], Cc, "same matrix, hierarchically clustered (average linkage) -- blocks are one idea wearing several names")
cb = fig.colorbar(im, ax=axs, fraction=0.015, pad=0.01); cb.set_label("Spearman rho")
fig.suptitle("VP / TPO / EMA / ATR feature correlation matrix -- measured where a filter acts, on the Donchian 10/10 07:00-11:00 breakout bars", fontsize=13, y=0.995)
fig.savefig(os.path.join(OUT, "vp_fig7_corr.png"), dpi=130, bbox_inches="tight"); plt.close(fig)
# near-duplicate pairs
pairs = [(a, b, C.loc[a, b]) for i, a in enumerate(C.columns) for b in C.columns[i + 1:] if abs(C.loc[a, b]) >= 0.9]
print(f"features {len(C)}; pairs with |rho| >= 0.9: {len(pairs)}")
for a, b, r in sorted(pairs, key=lambda t: -abs(t[2])): print(f"  {a:28s} {b:28s} {r:+.3f}")
# the survivor's row
s = C["tpo.prior_single_above_atr"].drop("tpo.prior_single_above_atr").sort_values(key=np.abs, ascending=False)
print("\nthe survivor's strongest correlations:"); print(s.head(8).to_string(float_format=lambda x: f"{x:+.3f}"))
