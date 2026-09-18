"""G2 -- the anomaly question answered directly, then ONE read of each reserved block.

THE HYPOTHESES ARE DECLARED HERE, BEFORE THE NUMBERS, because "find anomalies" has three distinct
readings and they make opposite predictions:
  H1  VOLATILITY CLUSTERING. An unusual bar precedes a LARGER forward range. If this is all that is
      there it is well known, unexploitable on its own, and must not be dressed up as an edge.
  H2  REVERSAL. An unusual bar precedes a move AGAINST its own direction -- the mechanism would be
      liquidity: whoever had to trade into a thin book overshoots and it comes back.
  H3  CONTINUATION. An unusual bar precedes a move WITH its own direction -- an information event.
H2 and H3 are mutually exclusive and both are testable as a SIGNED interaction, which is the only
form that can pay: `sign(bar return) x forward return`, conditioned on how anomalous the bar is.

Every score was fitted on the research block only and is applied unchanged to locked and forward.
The forward block is a DIFFERENT PROVIDER and is read once, last.
"""
import os, sys, pickle
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xdata as X, xfeat as XF

RNG = np.random.default_rng(23)
pd.set_option("display.width", 235)
L = lambda s: print("\n" + "=" * 116 + f"\n{s}\n" + "=" * 116)
print(__doc__)
Z = pickle.load(open("results/xanom/feat_cache.pkl", "rb"))
Xi, Yi, Xm, Ym = Z["Xi"], Z["Yi"], Z["Xm"], Z["Ym"]
res = np.asarray(Xi.index < Z["cut"])
loc = ~res
fwd = np.asarray(Xm.index > Z["iso_end"])
ANM = [c for c in Xi.columns if c.startswith("anm.")]
BLK = (("research", Xi, Yi, res), ("locked", Xi, Yi, loc), ("FORWARD", Xm, Ym, fwd))


def q5(x, y, nq=5):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 500:
        return None
    q = pd.qcut(pd.Series(x[ok]), nq, labels=False, duplicates="drop")
    g = pd.DataFrame(dict(q=q, y=y[ok])).groupby("q").y.agg(["size", "mean"])
    return g, ok.sum()


L("G2.1  H1 -- does an unusual bar precede a LARGER forward range?")
rows = []
for col in ANM:
    for bn, XX, YY, m in BLK:
        x = XX[col].to_numpy(float)[m]
        for hz in (4, 16, 96):
            y = YY[f"y.rng{hz}"].to_numpy(float)[m]
            r = q5(x, y)
            if r is None:
                continue
            g, n = r
            _b, t = XF.newey_west_t(x, y, lag=hz)
            rows.append(dict(score=col, block=bn, h=hz, n=n,
                             Q1=round(float(g["mean"].iloc[0]), 3), Q5=round(float(g["mean"].iloc[-1]), 3),
                             ratio=round(float(g["mean"].iloc[-1] / max(g["mean"].iloc[0], 1e-9)), 3),
                             nw_t=round(t, 1)))
H1 = pd.DataFrame(rows)
print(H1.to_string(index=False))
H1.to_csv("results/xanom/g2_h1_range.csv", index=False)
print("\n  Q5/Q1 is forward range in ATR units. A ratio well above 1 on every block is volatility")
print("  clustering, which is real and is NOT an edge -- it says nothing about direction.")

L("G2.2  H2 vs H3 -- the SIGNED test, which is the only form that can pay")
rows = []
for col in ANM:
    for bn, XX, YY, m in BLK:
        x = XX[col].to_numpy(float)[m]
        sgn = np.sign(XX["str.close_pos"].to_numpy(float)[m] - 0.5)   # the bar's own direction
        for hz in (1, 4, 16, 96):
            y = YY[f"y.ret{hz}"].to_numpy(float)[m] * sgn             # + = continuation, - = reversal
            r = q5(x, y)
            if r is None:
                continue
            g, n = r
            _b, t = XF.newey_west_t(x, y, lag=hz)
            rows.append(dict(score=col, block=bn, h=hz, n=n,
                             Q1=round(1e4 * float(g["mean"].iloc[0]), 2),
                             Q5=round(1e4 * float(g["mean"].iloc[-1]), 2),
                             spread_bp=round(1e4 * float(g["mean"].iloc[-1] - g["mean"].iloc[0]), 2),
                             nw_t=round(t, 2)))
H2 = pd.DataFrame(rows)
H2.to_csv("results/xanom/g2_h2_signed.csv", index=False)
for col in ANM:
    print(f"\n  --- {col}   (signed forward return in BASIS POINTS; + = continuation, - = reversal)")
    print(H2[H2.score == col].to_string(index=False))

L("G2.3  SIGN CONSISTENCY -- the only thing that separates a finding from a block")
piv = H2.pivot_table(index=["score", "h"], columns="block", values="Q5")
print(piv.round(2).to_string())
agree = H2.pivot_table(index=["score", "h"], columns="block", values="spread_bp")
agree = agree.dropna()
if len(agree):
    same = ((np.sign(agree["research"]) == np.sign(agree["locked"]))
            & (np.sign(agree["research"]) == np.sign(agree["FORWARD"])))
    print(f"\n  cells where research, locked AND forward agree on the SIGN of the Q5-Q1 spread: "
          f"{int(same.sum())} of {len(agree)}")
    print(agree[same].round(2).to_string() if same.any() else "  (none)")

L("G2.0  A CAVEAT ON THE FORWARD-RANGE LABEL, before its 152 BH passes are read")
print("""  `y.rng{h}` is the forward high-low divided by ATR(14) AT THE BAR. A bar whose ATR is already
  high therefore has a SMALLER normalised forward range almost by construction, which is why every
  volatility feature scores a large NEGATIVE IC against it (atr_pct500 at h=96: IC -0.533, t -42.9)
  and why 152 of 172 range tests clear BH while only 16 of 172 return tests do. Most of that is the
  DENOMINATOR, the same class as the collapsing-R traps this branch has recorded four times. The
  unnormalised version is printed beside it so the mechanical part can be separated from the real
  volatility clustering.""")
iso0 = X.load_iso()
atr0 = XF._atr(iso0.high.to_numpy(), iso0.low.to_numpy(), iso0.close.to_numpy(), 14)
rows = []
for col in ("vol.atr_pct500", "vol.rv24", "anm.ae_err"):
    x = Xi[col].to_numpy(float)[res]
    for hz in (16, 96):
        yn = Yi[f"y.rng{hz}"].to_numpy(float)[res]                       # normalised by ATR now
        yr = yn * atr0[res]                                              # back to USD
        for lab, y in (("normalised by ATR", yn), ("RAW USD range", yr)):
            m = np.isfinite(x) & np.isfinite(y)
            rows.append(dict(score=col, h=hz, label=lab,
                             ic=round(float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman")), 4)))
print()
print(pd.DataFrame(rows).pivot_table(index=["score", "h"], columns="label", values="ic").round(4).to_string())
print("\n  If the sign FLIPS between the two columns, the normalised result was the denominator.")

L("G2.4  THE COST FLOOR -- what any of this has to beat on gold")
c = np.exp(np.log(Xi.index.size))  # placeholder to keep the import honest
iso = X.load_iso()
atr = XF._atr(iso.high.to_numpy(), iso.low.to_numpy(), iso.close.to_numpy(), 14)
px = iso.close.to_numpy()
rt = X.COST_RT + 2 * X.SLIP
print(f"  round turn {rt:.2f} USD/oz;  median ATR(14) {np.nanmedian(atr):.3f} USD;  "
      f"median price {np.nanmedian(px):.1f}")
print(f"  cost as a fraction of a 1xATR stop: {rt/np.nanmedian(atr):.3f}")
print(f"  cost in BASIS POINTS of price: {1e4*rt/np.nanmedian(px):.2f} bp")
ret1 = np.diff(np.log(px))
sd_bp = 1e4 * np.nanstd(ret1)
print(f"\n  sd of a 15-minute log return: {sd_bp:.2f} bp")
print("  what an information coefficient is WORTH, against a "
      f"{1e4*rt/np.nanmedian(px):.2f} bp round turn:")
for ic in (0.01, 0.02, 0.046, 0.10, 0.20):
    val = ic * sd_bp
    print(f"    IC {ic:.3f} -> {val:5.2f} bp expected per trade   "
          f"= {val/(1e4*rt/np.nanmedian(px)):.2f}x the round turn"
          f"{'   <-- the best RETURN IC measured here' if abs(ic-0.046)<1e-9 else ''}")
print("  (`STUDY_V13` ran the identical arithmetic on US100 and found you need IC >= 0.10 at h=1.)")
print("\n  Any Q5-Q1 spread below that many basis points is not tradeable no matter how significant")
print("  it is. `STUDY_XAU_TWO_LAYER` measured the same floor: gold is gross-positive and net-")
print("  negative on 14 of 15 frozen cells, and the round turn is the whole difference.")
