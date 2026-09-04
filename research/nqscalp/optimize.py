"""Optimisation round for the NQ Scalping System.

RESEARCH BLOCK ONLY. The holdout has been read three times; nothing here touches
it. Walk-forward inside research is the out-of-sample proxy, and the matched
control is a FRONT gate, not a final check - running it only at the end is how
rules reach a holdout they then fail.

Everything is measured under the path-free `barclose` model. Optimising under the
intrabar model would tune the artifact, which is the opposite of the job.

Phase A is mechanistic: fixes with a reason, applied cumulatively, no search.
Phase B is a bounded search over what is left.
Phase C walk-forwards the survivors.
"""
import numpy as np, pandas as pd, sys, itertools, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
TM, ORD = "barclose", "adverse"
# full-size NQ: $20/point, so a $1.24 commission is 0.062 points, not 0.62
NQ = dict(point_value=20.0, qty=1)
RTH = dict(sess_start_h=8, sess_start_m=30, sess_end_h=10, sess_end_m=0)


def book(mask=R, cost_mult=1.0, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    tr = nqs.simulate(df, I, p, lo & mask, sh & mask, order=ORD, trail_mode=TM,
                      cost_mult=cost_mult)
    return tr, I, p


def gate(label, kw, n_draws=300, quiet=False):
    tr, I, p = book(**kw)
    if len(tr) < 40:
        print(f"  {label:<52} n={len(tr):<5} too few trades"); return None
    g = NC.score(df, I, p, tr, n_draws=n_draws, mask=R, order=ORD, trail_mode=TM)
    gross = book(cost_mult=0.0, **kw)[0].net_pts.mean()
    rt = 2 * 0.25 + 2 * p["commission"] / p["point_value"]
    g.update(gross=float(gross), round_turn=float(rt), label=label, kw=kw,
             net_usd=float(tr.net_usd.sum()), wr=float((tr.net_pts > 0).mean()),
             sess=int(tr.sess.nunique()))
    if not quiet:
        print(f"  {label:<52} n={g['n']:>5} gross{g['gross']:>+7.2f} net{g['exp']:>+7.2f} "
              f"ctrl{g['ctrl']:>+7.2f} excess{g['excess']:>+7.2f} z{g['z']:>+6.2f} "
              f"p={g['p']:.4f} RT={rt:.2f}")
    return g


print("=" * 132)
print("23. PHASE A - MECHANISTIC FIXES, APPLIED CUMULATIVELY (research block, barclose/adverse)")
print("    Each of these has a reason that is not 'it backtested better'. No search here.")
print("=" * 132)
STEPS = [
    ("A0  as written", {}),
    ("A1  + ATR-relative pullback threshold", dict(dist_units="atr", trail_arm_atr=15/13.0, trail_offset_atr=8/13.0)),
    ("A2  + ATR-relative trail (arm 1.0 / offset 0.5 ATR)", dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0, trail_offset_atr=0.5)),
    ("A3  + RTH only, 09:30-11:00 New York", dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0, trail_offset_atr=0.5, **RTH)),
    ("A4  + full-size NQ instead of MNQ", dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0, trail_offset_atr=0.5, **RTH, **NQ)),
]
phaseA = []
for lbl, kw in STEPS:
    g = gate(lbl, kw)
    if g: phaseA.append(g)
json.dump(phaseA, open(OUT + "phaseA.json", "w"), indent=2, default=str)
BASE = {**STEPS[-1][1]}
print(f"\n  carrying forward: {BASE}")


print("\n" + "=" * 132)
print("24. PHASE B - THE MOVING-AVERAGE STRUCTURE, WHICH IS WHAT THE ENTRY ACTUALLY IS")
print("    B1: the trend gate and the pullback target. Matched control is the FRONT gate, not a final check.")
print("=" * 132)
TREND_N = [34, 50, 89, 144, 200]
TREND_T = ["ema", "sma", "hma"]
FAST_N = [5, 8, 13, 21]
SLOW_N = [21, 34, 50]
cells = list(itertools.product(TREND_N, TREND_T, FAST_N, SLOW_N))
cells = [c for c in cells if c[2] < c[3]]
print(f"  {len(cells)} configurations (fast < slow enforced)")
rows = []
for i, (tn, tt, fn, sn) in enumerate(cells):
    kw = {**BASE, "trend_ema": tn, "trend_ma": tt, "fast_ema": fn, "slow_ema": sn}
    g = gate(f"{tt}{tn} pull {fn}/{sn}", kw, n_draws=120, quiet=True)
    if g:
        rows.append(dict(trend_n=tn, trend_t=tt, fast=fn, slow=sn, n=g["n"],
                         gross=g["gross"], exp=g["exp"], ctrl=g["ctrl"],
                         excess=g["excess"], z=g["z"], p=g["p"], wr=g["wr"]))
    if (i + 1) % 20 == 0:
        print(f"    {i+1}/{len(cells)}")
Bdf = pd.DataFrame(rows)
Bdf.to_csv(OUT + "phaseB_ma.csv", index=False)
print(f"\n  cells with net>0: {(Bdf.exp>0).sum()}/{len(Bdf)}   "
      f"with excess>0 and p<0.05: {((Bdf.excess>0)&(Bdf.p<0.05)).sum()} "
      f"(chance ~{0.05*len(Bdf):.0f})")
print(f"  net expectancy: p5 {Bdf.exp.quantile(.05):+.2f}  median {Bdf.exp.median():+.2f}  "
      f"p95 {Bdf.exp.quantile(.95):+.2f}")
print("\n  MARGINALS - is any one ingredient carrying it?")
for col in ("trend_t", "trend_n", "fast", "slow"):
    m = Bdf.groupby(col).agg(exp=("exp", "mean"), excess=("excess", "mean"),
                             pos=("exp", lambda s: (s > 0).mean()), n=("exp", "size"))
    print(f"    by {col}: " + "   ".join(
        f"{k}: exp{r.exp:+.2f} exc{r.excess:+.2f} {r.pos:.0%}+" for k, r in m.iterrows()))
print("\n  TOP 12 BY EXCESS OVER THE MATCHED CONTROL")
print(f"  {'trend':>10} {'pull':>8} {'n':>5} {'gross':>7} {'net':>7} {'ctrl':>7} {'excess':>7} {'z':>6} {'p':>7} {'wr':>6}")
for _, x in Bdf.sort_values("excess", ascending=False).head(12).iterrows():
    print(f"  {x.trend_t + str(int(x.trend_n)):>10} {int(x.fast)}/{int(x.slow):<6} {int(x.n):>5} "
          f"{x.gross:>+7.2f} {x.exp:>+7.2f} {x.ctrl:>+7.2f} {x.excess:>+7.2f} {x.z:>+6.2f} "
          f"{x.p:>7.4f} {x.wr:>6.1%}")
