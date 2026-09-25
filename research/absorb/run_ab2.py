"""The exit question done fairly, plus cross-market. The submitted design has ONLY a stop and a
trail -- remove the trail and there is no profit-taking exit at all, so 'no trail' is not a like-
for-like arm (it holds until stopped: 110 trades, 20-bar median). Every no-trail cell here is
given a real exit (a target or a max hold) so the comparison means something."""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_core as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
def hdr(): print(f"  {'':50s}{'n':>6s}{'%/trade':>9s}{'PF':>7s}{'win%':>6s}{'$ 1 MNQ':>10s}{'hold':>6s}  exits")
def row(nm, t):
    if len(t) == 0: print(f"  {nm:50s}     0"); return
    s = A.stats(t); mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    print(f"  {nm:50s}{s['n']:>6d}{s['pct']:>9.4f}{s['pf']:>7.3f}{s['win']:>6.1f}{s['usd_tot']:>10,.0f}{s['hold']:>6.0f}  "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))

MK, TF = "NQ", 15
D = A.build(MK, TF); RES = D["blocks"]["research"]
LV = ("mid", "1h", "4h")
bl = np.where(RES, A.signals(D, levels=LV, vol_min=0.1), 0)

line("A. THE EXIT, TESTED FAIRLY -- every no-trail cell gets a real exit; RESEARCH block")
hdr()
print("  -- trailing stop, tightening (the asked value is 1.0/1.0) --")
for arm, off in ((0.25, 0.25), (0.5, 0.25), (0.5, 0.5), (0.75, 0.5), (1.0, 1.0), (2.0, 2.0)):
    row(f"  trail {arm} / {off} ATR", A.run(D, bl, stop=1.5, trail=True, t_arm=arm, t_off=off))
print("  -- no trail, but with a TARGET (so the trade can end in profit) --")
for tg in (0.5, 1.0, 1.5, 2.0, 3.0):
    row(f"  no trail, target {tg} ATR", A.run(D, bl, stop=1.5, trail=False, tgt=tg))
print("  -- no trail, no target, but a MAX HOLD in bars --")
for mh in (4, 8, 16, 32, 96):
    row(f"  no trail, max hold {mh} bars", A.run(D, bl, stop=1.5, trail=False, max_hold=mh))
print("  -- the degenerate arm, shown so the grid marginal is not misread --")
row("  no trail, no target, no hold cap", A.run(D, bl, stop=1.5, trail=False))

line("B. DROP-ONE at the best-behaved geometry, and what absorption is worth")
best = dict(stop=1.5, trail=True, t_arm=0.5, t_off=0.5)
hdr()
row("full rule (mid + swings, absorption, tight trail)", A.run(D, bl, **best))
row("  - absorption removed", A.run(D, np.where(RES, A.signals(D, levels=LV, need_absorb=False), 0), **best))
row("  - levels removed (absorption alone)", A.run(D, np.where(RES, np.where((D["scaled"] >= 0.1) & D["lower_zone"], 1, np.where((D["scaled"] >= 0.1) & D["upper_zone"], -1, 0)), 0), **best))
for vm in (0.5, 1.0, 2.0, 4.0):
    row(f"  absorption threshold scaledVol >= {vm}", A.run(D, np.where(RES, A.signals(D, levels=LV, vol_min=vm), 0), **best))
row("  midline only", A.run(D, np.where(RES, A.signals(D, levels=("mid",), vol_min=0.1), 0), **best))
row("  swings only", A.run(D, np.where(RES, A.signals(D, levels=("1h", "4h"), vol_min=0.1), 0), **best))
row("  longs only", A.run(D, np.where(RES, A.signals(D, levels=LV, vol_min=0.1, side="long"), 0), **best))
row("  shorts only", A.run(D, np.where(RES, A.signals(D, levels=LV, vol_min=0.1, side="short"), 0), **best))
row("  zero cost", A.run(D, bl, fee=0.0, slip=0.0, **best))
row("  2x cost", A.run(D, bl, cost_mult=2.0, **best))

line("C. CONTROLS at the best-behaved geometry (research block)")
def controls(sig, kw, ndraw=300):
    rng = np.random.default_rng(7)
    real = int((sig != 0).sum())
    elig = np.where(RES & np.isfinite(D["atr"]) & (D["atr"] > 0))[0]
    elig = elig[(elig > 300) & (elig < D["n"] - 3)]
    pool = sig[sig != 0]
    ce = []
    for _ in range(ndraw):
        pick = np.sort(rng.choice(elig, size=real, replace=False))
        s2 = np.zeros(D["n"], np.int64); s2[pick] = rng.permutation(pool)[:len(pick)]
        t = A.run(D, s2, **kw); ce.append(t["pct"].mean() if len(t) else np.nan)
    raw = np.where(RES, A.signals(D, levels=LV, need_absorb=False), 0)
    idx = np.where(raw != 0)[0]; cf = []
    for _ in range(ndraw):
        pick = rng.choice(idx, size=min(real, len(idx)), replace=False)
        s2 = np.zeros(D["n"], np.int64); s2[pick] = raw[pick]
        t = A.run(D, s2, **kw); cf.append(t["pct"].mean() if len(t) else np.nan)
    return np.array(ce), np.array(cf)
t = A.run(D, bl, **best); obs = t["pct"].mean()
ce, cf = controls(bl, best)
print(f"  tight-trail rule: n={len(t)}  observed {obs:+.4f}  PF {A.stats(t)['pf']:.3f}")
print(f"     random ENTRY  median {np.nanmedian(ce):+.4f}  5-95% [{np.nanpercentile(ce,5):+.4f}, {np.nanpercentile(ce,95):+.4f}]  p {np.mean(ce>=obs):.3f}")
print(f"     random FILTER median {np.nanmedian(cf):+.4f}  5-95% [{np.nanpercentile(cf,5):+.4f}, {np.nanpercentile(cf,95):+.4f}]  p {np.mean(cf>=obs):.3f}")

line("D. CROSS-MARKET -- the SAME rule, unchanged, on feeds that had no part in any of this")
print("  NOTE: US100/US30 carry TICK volume, so their absorption is a proxy of a proxy.")
hdr()
for mk in ("US100", "US30"):
    Dx = A.build(mk, 15)
    for bn, bm in Dx["blocks"].items():
        s = np.where(bm, A.signals(Dx, levels=LV, vol_min=0.1), 0)
        row(f"  {mk} 15m tight trail [{bn}]", A.run(Dx, s, **best))
