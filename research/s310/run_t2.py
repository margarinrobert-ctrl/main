"""T2 -- parameter stress: the geometry grid read by MARGINAL AVERAGE, and the one-rung box.

The top row of a grid is the maximum of as many draws as the grid has cells. What a grid can
honestly say is what each SETTING does averaged over everything else, and whether the shipped cell
sits on a plateau or a spike.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
D, F, base = T.build(10)
P = dict(k=int(os.environ.get("PK", 3)), w=int(os.environ.get("PW", 20)))
print(f"  base cell: k{P['k']}/w{P['w']} at 10 minutes")
lg, sh = SG.s3_flow_exhaustion(D, F, P)

STOPS = (1.5, 2.0, 2.5, 3.0, 4.0, 6.0)
TGTS = (0.0, 1.5, 2.0, 3.0, 4.0)
BES = (0.0, 1.0, 1.5)
ARMS = (0.0, 1.0, 1.5)
TRS = (0.75, 1.0, 1.5)
rows = []
for st, tg, be, ar, tr in itertools.product(STOPS, TGTS, BES, ARMS, TRS):
    if ar == 0.0 and tr != 1.0:      # the trail distance is INERT when the trail is off
        continue
    g = dict(stop=st, tgt=tg, be=be, be_off=0.25, arm=ar, tr=tr)
    t = T.run(D, lg, sh, g)
    a, b = T.stats(t, D, 0), T.stats(t, D, 1)
    rows.append(dict(stop=st, tgt=tg, be=be, arm=ar, tr=tr,
                     n_r=a["n"], pts_r=a["pts"], pf_r=a["pf"], sh_r=a["sharpe"], dd_r=a["dd"],
                     n_l=b["n"], pts_l=b["pts"], pf_l=b["pf"], sh_l=b["sharpe"], dd_l=b["dd"]))
Gd = pd.DataFrame(rows)
Gd.to_csv(R + "t2_geometry.csv", index=False)
sc = Gd[(Gd.n_r >= 30) & (Gd.n_l >= 20)]
print(f"\n  {len(Gd)} declared cells ({len(Gd)} scorable after the inert-axis collapse), "
      f"{len(sc)} clear the trade floor")
print(f"  profitable on research {(sc.pts_r>0).mean():.1%}   on LOCKED {(sc.pts_l>0).mean():.1%}")
print(f"  corr(research pts, locked pts): {np.corrcoef(sc.pts_r, sc.pts_l)[0,1]:+.3f} Pearson  "
      f"{sc.pts_r.corr(sc.pts_l, method='spearman'):+.3f} Spearman")

print("\n" + "=" * 118)
print("T2.1  MARGINAL AVERAGE PER AXIS -- never the top row")
print("=" * 118)
for ax in ("stop", "tgt", "be", "arm", "tr"):
    m = sc.groupby(ax).agg(n=("pts_r", "size"), res_pts=("pts_r", "mean"),
                           lок=("pts_l", "mean"), res_pf=("pf_r", "mean"),
                           lok_pf=("pf_l", "mean"), res_sh=("sh_r", "mean"),
                           lok_sh=("sh_l", "mean")).round(3)
    m.columns = ["cells", "res pts", "lok pts", "res PF", "lok PF", "res Sh", "lok Sh"]
    print(f"\n  --- {ax} ---")
    print(m.to_string())

print("\n" + "=" * 118)
print("T2.2  THE SHIPPED CELL'S OWN NEIGHBOURHOOD -- plateau or spike?")
print("=" * 118)
DEF = dict(stop=3.0, tgt=0.0, be=1.0, arm=1.0, tr=1.0)
d = sc.copy()
for k, v in DEF.items():
    d = d[np.isclose(d[k], v)] if k == "stop" else d
box = sc[(sc.stop.between(2.0, 4.0)) & (sc.tgt.isin([0.0, 3.0, 4.0])) &
         (sc.be.isin([0.0, 1.0])) & (sc.arm.isin([0.0, 1.0])) & (sc.tr.isin([0.75, 1.0, 1.5]))]
print(f"  one-rung box around the default: {len(box)} cells")
print(f"    profitable on research {(box.pts_r>0).mean():.1%}   on LOCKED {(box.pts_l>0).mean():.1%}")
print(f"    research pts  p25 {box.pts_r.quantile(.25):+.2f}  median {box.pts_r.median():+.2f}  "
      f"p75 {box.pts_r.quantile(.75):+.2f}")
print(f"    LOCKED  pts   p25 {box.pts_l.quantile(.25):+.2f}  median {box.pts_l.median():+.2f}  "
      f"p75 {box.pts_l.quantile(.75):+.2f}")
dflt = sc[np.isclose(sc.stop, 3.0) & np.isclose(sc.tgt, 0.0) & np.isclose(sc.be, 1.0) &
          np.isclose(sc.arm, 1.0) & np.isclose(sc.tr, 1.0)]
if len(dflt):
    r = dflt.iloc[0]
    print(f"    the DEFAULT cell itself: research {r.pts_r:+.3f} PF {r.pf_r:.3f}; "
          f"LOCKED {r.pts_l:+.3f} PF {r.pf_l:.3f}")
    print(f"    share of the box BEATING it on research {(box.pts_r>r.pts_r).mean():.1%}, "
          f"on LOCKED {(box.pts_l>r.pts_l).mean():.1%}")
    print("    A cell most of its own neighbourhood beats was not cherry-picked from a spike;")
    print("    a cell almost none of them beats is sitting on one (STUDY_V64_MONTECARLO).")
print(f"\ntotal {time.time()-t0:.0f}s")
