"""The combined strategy: grid read by marginal average, the ask as specified, its ablations, and
two matched controls. RESEARCH BLOCK ONLY except the single pre-declared locked read at the end."""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_core as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
def hdr(): print(f"  {'':52s}{'n':>6s}{'%/trade':>9s}{'PF':>7s}{'win%':>6s}{'$ 1 MNQ':>10s}{'hold':>6s}  exits")
def row(nm, t):
    if len(t) == 0: print(f"  {nm:52s}     0"); return
    s = A.stats(t)
    mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    print(f"  {nm:52s}{s['n']:>6d}{s['pct']:>9.4f}{s['pf']:>7.3f}{s['win']:>6.1f}{s['usd_tot']:>10,.0f}{s['hold']:>6.0f}  "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))

MK, TF = "NQ", 15
D = A.build(MK, TF)
RES = D["blocks"]["research"]

LEVELS = {"mid only": ("mid",), "1H+4H swings": ("1h", "4h"), "mid + swings": ("mid", "1h", "4h"),
          "all six": ("mid", "1h", "4h", "D", "W", "M")}

line("A. THE DECLARED GRID -- levels x trail x stop x side x absorption threshold; RESEARCH block")
rows = []
for lname, lv in LEVELS.items():
    for vmin in (0.1, 1.0, 2.0):
        s = A.signals(D, levels=lv, vol_min=vmin)
        for sd in ("both", "long", "short"):
            ss = A.signals(D, levels=lv, vol_min=vmin, side=sd)
            for trail in (True, False):
                for stop in (1.0, 1.5, 2.5):
                    sb = ss.copy(); sb[~RES] = 0
                    t = A.run(D, sb, stop=stop, trail=trail)
                    if len(t) < 30: continue
                    st = A.stats(t)
                    rows.append(dict(levels=lname, vmin=vmin, side=sd, trail=trail, stop=stop,
                                     n=st["n"], pct=st["pct"], pf=st["pf"], win=st["win"], tot=st["tot"]))
G = pd.DataFrame(rows)
print(f"  {len(G)} scorable cells (>=30 trades); share net-profitable {100*(G.pct>0).mean():.1f}%; median %/trade {G.pct.median():+.4f}")
print("\n  MARGINAL AVERAGE PER AXIS -- read this, never the top row:")
for ax in ("levels", "vmin", "side", "trail", "stop"):
    print(f"   {ax:>8}: " + "   ".join(f"{k}: {v.pct.mean():+.4f} (PF {v.pf.mean():.2f}, n~{v.n.mean():.0f})"
                                        for k, v in G.groupby(ax)))
print("\n  top 8 cells by %/trade (the max of many draws -- shown for shape, not as a selection):")
print(G.sort_values("pct", ascending=False).head(8).to_string(index=False))

line("B. THE ASK AS SPECIFIED -- mid + 1H/4H swings, absorption on, 1.5 ATR stop, ATR trail; RESEARCH")
base = A.signals(D, levels=("mid", "1h", "4h"), vol_min=0.1)
bl = base.copy(); bl[~RES] = 0
hdr()
row("as asked (trail 1.0/1.0 ATR)", A.run(D, bl, stop=1.5, trail=True))
row("  - no trail", A.run(D, bl, stop=1.5, trail=False))
row("  - no absorption requirement", A.run(D, np.where(RES, A.signals(D, levels=("mid","1h","4h"), need_absorb=False), 0), stop=1.5, trail=True))
row("  - no absorption, no trail", A.run(D, np.where(RES, A.signals(D, levels=("mid","1h","4h"), need_absorb=False), 0), stop=1.5, trail=False))
row("  - swings only (no midline)", A.run(D, np.where(RES, A.signals(D, levels=("1h","4h"), vol_min=0.1), 0), stop=1.5, trail=True))
row("  - midline only (no swings)", A.run(D, np.where(RES, A.signals(D, levels=("mid",), vol_min=0.1), 0), stop=1.5, trail=True))
row("  longs only", A.run(D, np.where(RES, A.signals(D, levels=("mid","1h","4h"), vol_min=0.1, side="long"), 0), stop=1.5, trail=True))
row("  shorts only", A.run(D, np.where(RES, A.signals(D, levels=("mid","1h","4h"), vol_min=0.1, side="short"), 0), stop=1.5, trail=True))
row("  zero cost", A.run(D, bl, stop=1.5, trail=True, fee=0.0, slip=0.0))
print("\n  the trail ladder at the asked geometry:")
hdr()
for arm, off in ((0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (3.0, 2.0)):
    row(f"  trail arm {arm} / offset {off} ATR", A.run(D, bl, stop=1.5, trail=True, t_arm=arm, t_off=off))
row("  NO TRAIL", A.run(D, bl, stop=1.5, trail=False))

line("C. TWO MATCHED CONTROLS on the asked configuration (research block)")
def ctrl_entry(sig, stop, trail, ndraw=300, seed=1):
    rng = np.random.default_rng(seed)
    real = int((sig != 0).sum())
    elig = np.where(RES & np.isfinite(D["atr"]) & (D["atr"] > 0))[0]
    elig = elig[(elig > 300) & (elig < D["n"] - 3)]
    pool = sig[sig != 0]
    out = []
    for _ in range(ndraw):
        pick = np.sort(rng.choice(elig, size=real, replace=False))
        s2 = np.zeros(D["n"], np.int64); s2[pick] = rng.permutation(pool)[:len(pick)]
        t = A.run(D, s2, stop=stop, trail=trail)
        out.append(t["pct"].mean() if len(t) else np.nan)
    return np.array(out)
def ctrl_filter(lv, stop, trail, keep_n, ndraw=300, seed=2):
    """same-selectivity random filter: keep the same number of LEVEL-TOUCH bars at random,
    instead of the ones absorption picks"""
    rng = np.random.default_rng(seed)
    raw = A.signals(D, levels=lv, need_absorb=False); raw = np.where(RES, raw, 0)
    idx = np.where(raw != 0)[0]
    out = []
    for _ in range(ndraw):
        pick = rng.choice(idx, size=min(keep_n, len(idx)), replace=False)
        s2 = np.zeros(D["n"], np.int64); s2[pick] = raw[pick]
        t = A.run(D, s2, stop=stop, trail=trail)
        out.append(t["pct"].mean() if len(t) else np.nan)
    return np.array(out)

for nm, trail in (("as asked (trail ON)", True), ("no trail", False)):
    sig = bl
    t = A.run(D, sig, stop=1.5, trail=trail); obs = t["pct"].mean()
    ce = ctrl_entry(sig, 1.5, trail)
    cf = ctrl_filter(("mid", "1h", "4h"), 1.5, trail, int((sig != 0).sum()))
    print(f"  {nm}: n={len(t)}  observed {obs:+.4f}")
    print(f"     random ENTRY  median {np.nanmedian(ce):+.4f}  5-95% [{np.nanpercentile(ce,5):+.4f}, {np.nanpercentile(ce,95):+.4f}]  p {np.mean(ce>=obs):.3f}")
    print(f"     random FILTER median {np.nanmedian(cf):+.4f}  5-95% [{np.nanpercentile(cf,5):+.4f}, {np.nanpercentile(cf,95):+.4f}]  p {np.mean(cf>=obs):.3f}")
G.to_parquet("results/absorb/grid.parquet")
