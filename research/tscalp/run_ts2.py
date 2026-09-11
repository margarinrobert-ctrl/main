"""The 'most robust version' read honestly. The drop-one consensus on research is EMA150 + the
20>50>200 state with the pullback REMOVED (it is also the grid's top real cell and the marginal
winner on two of three axes). It was chosen after ~40 research cells were seen, so its US30 locked
read is DESCRIPTIVE with that multiplicity stated; US100 and NQ chose nothing and are the honest
held-back test. Neighbourhood on research first, so a spike cannot be mistaken for a plateau."""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ts_core as T
from core import _atr_wilder
warnings.filterwarnings("ignore")
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
def hdr(): print(f"  {'':56s}{'n':>6s}{'R/trade':>9s}{'PF':>7s}{'win%':>6s}{'pts/tr':>8s}{'$ 1u':>9s}{'maxDD':>8s}{'Sharpe':>7s}  exits")
def row(nm, t):
    if len(t) < 5: print(f"  {nm:56s}{len(t):>6d}   (too few)"); return
    s = T.stats(t); mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    print(f"  {nm:56s}{s['n']:>6d}{s['R']:>9.4f}{s['pf']:>7.3f}{s['win']:>6.1f}{s['pts']:>8.2f}{s['usd']:>9,.0f}{s['dd']:>8,.0f}{s['sharpe']:>7.2f}  "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))
CAND = dict(ema150="above", cross="state")
P = T.PRESET

line("A. NEIGHBOURHOOD of the candidate on US30 research -- EMA lengths perturbed one rung each way")
D = T.build("US30", 15); RES = D["blocks"]["research"]; LCK = ~RES
atr = _atr_wilder(D["h"], D["l"], D["c"], P["atr_len"])
hdr()
row("candidate: EMA150 above + 20>50>200 state, no pullback", T.run(D, ok=T.gate(D, atr=atr, **CAND) & RES))
for fast, slow, trend in ((15, 40, 150), (25, 60, 250), (20, 50, 100), (20, 50, 300), (10, 30, 200), (30, 80, 200)):
    Dn = dict(D, ema20=T._ema(D["c"], fast), ema50=T._ema(D["c"], slow), ema200=T._ema(D["c"], trend))
    row(f"  EMA {fast}/{slow} aligned with {trend}", T.run(Dn, ok=T.gate(Dn, atr=atr, **CAND) & RES))
print("  and the script's exits on the candidate:")
row("  candidate + NO take profit", T.run(D, ok=T.gate(D, atr=atr, **CAND) & RES, cfg=dict(tp_r=0.0)))
row("  candidate + one unit", T.run(D, ok=T.gate(D, atr=atr, **CAND) & RES, cfg=dict(max_units=1, pyr_step=0.0)))
row("  candidate + no flatten", T.run(D, ok=T.gate(D, atr=atr, **CAND) & RES, cfg=dict(flat0=24*60, flat1=24*60)))
row("  candidate, 2x cost", T.run(D, ok=T.gate(D, atr=atr, **CAND) & RES, cost_mult=2.0))

line("B. HELD-BACK MARKETS -- the candidate FROZEN on US100 and NQ, every block, beside the shipped script")
hdr()
for mk in ("US100", "NQ"):
    Dx = T.build(mk, 15); ax = _atr_wilder(Dx["h"], Dx["l"], Dx["c"], P["atr_len"])
    for bn, bm in Dx["blocks"].items():
        row(f"  {mk} [{bn}] shipped script", T.run(Dx, ok=bm))
        row(f"  {mk} [{bn}] candidate", T.run(Dx, ok=T.gate(Dx, atr=ax, **CAND) & bm))
        row(f"  {mk} [{bn}] candidate, no flatten", T.run(Dx, ok=T.gate(Dx, atr=ax, **CAND) & bm, cfg=dict(flat0=24*60, flat1=24*60)))

line("C. US30 LOCKED -- ONE read, DESCRIPTIVE: the candidate was picked after ~40 research cells were seen")
hdr()
t = T.run(D, ok=T.gate(D, atr=atr, **CAND) & LCK)
row("  candidate [locked, pooled]", t)
for bn in ("validation", "test"):
    row(f"    {bn}", t[t.block == bn])
# a same-selectivity random filter on the locked block, for the record (not a selection)
rng = np.random.default_rng(9)
from core import _rolling_max
hi1 = _rolling_max(D["h"], P["entry1"]); hi2 = _rolling_max(D["h"], P["entry2"])
sigb = np.zeros(D["n"], bool); sigb[1:] = (D["h"][1:] > hi1[:-1]) | (D["h"][1:] > hi2[:-1])
sigb &= (D["mod"] >= P["win0"]) & (D["mod"] < P["win1"]); sigb[:250] = False
g = T.gate(D, atr=atr, **CAND); keep = int((g & sigb & LCK).sum()); pool = np.where(sigb & LCK)[0]
obs = t["R"].mean(); cf = []
for _ in range(300):
    m = np.zeros(D["n"], bool); m[rng.choice(pool, size=min(keep, len(pool)), replace=False)] = True
    tt = T.run(D, ok=m); cf.append(tt["R"].mean() if len(tt) else np.nan)
cf = np.array(cf)
print(f"  locked random-filter control: median {np.nanmedian(cf):+.4f}  5-95% [{np.nanpercentile(cf,5):+.4f}, {np.nanpercentile(cf,95):+.4f}]  p {np.mean(cf>=obs):.3f}")
v = t["pnl"].to_numpy(); days = t["sess"].to_numpy()
_u, inv = np.unique(days, return_inverse=True); nd = inv.max() + 1; by = [np.flatnonzero(inv == j) for j in range(nd)]
bs = np.array([v[np.concatenate([by[j] for j in rng.integers(0, nd, nd)])].mean() for _ in range(3000)])
def mdd(r): e = np.cumsum(r); return float(np.max(np.maximum.accumulate(e) - e))
pm = np.array([mdd(rng.permutation(v)) for _ in range(3000)]); rd = mdd(v)
print(f"  locked day-block bootstrap: mean {v.mean():+.3f} pts  95% CI [{np.quantile(bs,.025):+.3f}, {np.quantile(bs,.975):+.3f}]  P(mean<=0) {(bs<=0).mean():.3f}")
print(f"  locked permutation: realised DD {rd:,.0f}  MC p50 {np.median(pm):,.0f}  p95 {np.quantile(pm,.95):,.0f}  p99 {np.quantile(pm,.99):,.0f}  realised pctile {(pm<=rd).mean():.2f}")
