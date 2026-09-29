"""The base candidates: a DECLARED 2 x 3 x 2 x 2 grid read by marginal, a stop ladder, both sides,
a random-entry control, and the same rule on NQ 15m and US100 15m. Research block only."""
from __future__ import annotations
import os, sys, warnings, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e48_core as E
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 122 + f"\n{t}\n" + "=" * 122)
def hdr(): print(f"  {'':52s}{'n':>6s}{'%/trade':>10s}{'PF':>8s}{'win%':>7s}{'R':>8s}{'$ 1 MNQ':>10s}{'hold':>6s}   exits")
def row(nm, t):
    s = E.stats(t); mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict() if len(t) else {}
    print(f"  {nm:52s}{s['n']:>6d}{s['pct']:>10.4f}{s['pf']:>8.3f}{s['win']:>7.1f}{s['R']:>8.3f}{s['usd_tot']:>10,.0f}{s['hold']:>6.0f}   " + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))
R = lambda t: t[t.block == "research"]

D = E.build("NQ", 5)
line("A. THE DECLARED GRID -- cross {fresh, state} x VWAP {off, state, touch} x trail {on, off} x flatten {on, off}; NQ 5m research")
rows = []
for cm, vm, tr, fl in itertools.product(("cross", "state"), ("off", "state", "touch"), (True, False), (True, False)):
    t = R(E.run(D, E.signals(D, cm, 5, vm), trail=tr, flat=fl)); s = E.stats(t)
    rows.append(dict(cross=cm, vwap=vm, trail=tr, flatten=fl, n=s["n"], pct=s["pct"], pf=s["pf"], win=s["win"], usd=s["usd_tot"]))
G = pd.DataFrame(rows); G.to_parquet("results/ema48/grid.parquet")
print(f"  24 cells; share net-profitable {100*(G.pct>0).mean():.1f}%; median %/trade {G.pct.median():+.4f}")
for ax in ("cross", "vwap", "trail", "flatten"):
    print(f"  {ax}: " + "   ".join(f"{v}: {G[G[ax]==v].pct.mean():+.4f} (PF {G[G[ax]==v].pf.mean():.3f}, n~{G[G[ax]==v].n.median():.0f})" for v in G[ax].unique()))
print("\n  the full grid, sorted -- printed because the marginals are the answer, not the top row:")
print(G.sort_values("pct", ascending=False).to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

line("B. THE ASK AS STATED -- fresh cross, VWAP state, 1.5 ATR stop, ATR trail 1.0/1.0, flatten -- and its ablations")
hdr()
base_sig = E.signals(D, "cross", 5, "state")
t0 = R(E.run(D, base_sig)); row("as asked", t0)
row("  - no trail", R(E.run(D, base_sig, trail=False)))
row("  - no VWAP gate", R(E.run(D, E.signals(D, "cross", 5, "off"))))
row("  - no flatten (hold overnight)", R(E.run(D, base_sig, flat=False)))
row("  - no trail, no flatten", R(E.run(D, base_sig, trail=False, flat=False)))
row("  longs only", R(E.run(D, np.where(base_sig == 1, 1, 0))))
row("  shorts only", R(E.run(D, np.where(base_sig == -1, -1, 0))))
row("  VWAP touch instead of state", R(E.run(D, E.signals(D, "cross", 5, "touch"))))
row("  zero cost", R(E.run(D, base_sig, cost=0.0, slip=0.0)))

line("C. THE STOP LADDER (as asked otherwise) -- V18 found this axis monotone toward WIDER on every market")
hdr()
for st in (1.0, 1.5, 2.0, 2.5, 3.0):
    row(f"stop {st} ATR", R(E.run(D, base_sig, stop=st)))
print("  and the trail arm/offset ladder, stop 1.5:")
for arm, off in ((0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (2.0, 1.0), (2.0, 2.0)):
    row(f"trail arm {arm} / off {off} ATR", R(E.run(D, base_sig, t_arm=arm, t_off=off)))

line("D. RANDOM-ENTRY CONTROL -- same session, same side mix, same geometry and exits, random RTH bar; 300 draws")
rng = np.random.default_rng(5)
for nm, sig, tr in (("as asked", base_sig, True), ("as asked, no trail", base_sig, False)):
    t = R(E.run(D, sig, trail=tr)); obs = t["pct"].mean()
    ins = D["rth"] & (D["mod"] < E.RTH1) & D["blocks"]["research"] & np.isfinite(D["vwap"]); pool = np.flatnonzero(ins)
    nL, nS = int((t.side == 1).sum()), int((t.side == -1).sum()); draws = np.zeros(300)
    for d in range(300):
        pick = np.sort(rng.choice(pool, size=min(len(pool), 3 * len(t)), replace=False))
        so = np.zeros(D["n"], np.int64); so[pick] = rng.choice([1, -1], size=len(pick), p=[nL / (nL + nS), nS / (nL + nS)])
        tc = R(E.run(D, so, trail=tr)); draws[d] = tc["pct"].mean() if len(tc) else 0.0
    print(f"  {nm:22s} n {len(t):5d}  observed {obs:+.4f}  control median {np.median(draws):+.4f}  5-95% [{np.quantile(draws,.05):+.4f}, {np.quantile(draws,.95):+.4f}]  p {(draws>=obs).mean():.3f}")

line("E. THE SAME RULE ON NQ 15m AND US100 15m (both blocks -- these are reads, not selections)")
hdr()
for m, tf in (("NQ", 15), ("US100", 15)):
    Dx = E.build(m, tf); sg = E.signals(Dx, "cross", 5, "state")
    for b in ("research", "locked"):
        t = E.run(Dx, sg); row(f"{m} {tf}m as asked [{b}]", t[t.block == b])
        t = E.run(Dx, sg, trail=False); row(f"{m} {tf}m no trail [{b}]", t[t.block == b])
print(f"  US100 volume is {E.build('US100', 15)['vol_kind']} -- its VWAP is a proxy.")
