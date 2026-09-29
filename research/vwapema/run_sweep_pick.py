"""TWO RANKINGS from the 108,000-cell sweep, and ONE locked read of each.

  * TOP ROW by research mean R -- the maximum of ~57,000 positive draws, which is what an optimiser
    reports and what `STUDY_V60` found to be a spike more often than not.
  * NEIGHBOURHOOD-BEST -- the highest mean over its own +-1 rung box on all SEVEN ordered axes
    (a 3^7 = 2,187-cell box, computed as a uniform filter over the reshaped grid). `STUDY_V38`
    found this beat the top row on every fresh-market cell; `STUDY_V60` found a perfect plateau is
    still not evidence, so it is a candidate, not proof.
Both are scored against the same matched random entry they would face on either block.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.ndimage import uniform_filter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(2718)
pd.set_option("display.width", 220)
print(__doc__)
G = pd.read_parquet("results/vwapema/sweep100k.parquet")
AX = dict(ema_slow=[100, 150, 200, 250, 300, 400], ema_pull=[20, 34, 50, 70, 90, 120],
          wick=[1.5, 2.0, 3.0], vol=[1.0, 1.1, 1.3, 1.5, 1.8], range=[0.4, 0.6, 0.8, 1.1],
          stop=[0.25, 0.5, 0.75, 1.0, 1.5], tgt=[2.0, 3.0, 4.0, 6.0, 0.0])  # 0 = none, at the wide end
SESS = ["ny", "utc"]
print(f"  {len(G):,} cells; {100*(G.R_res>0).mean():.1f}% profitable on research")
print(f"  corr(research R, locked R) Pearson {np.corrcoef(G.R_res, G.R_lock.fillna(0))[0,1]:+.3f}, "
      f"Spearman {G[['R_res','R_lock']].corr(method='spearman').iloc[0,1]:+.3f}")

# ---- reshape to an 8-D grid and take the +-1 box mean on the seven ordered axes
idx = {k: {v: i for i, v in enumerate(vs)} for k, vs in AX.items()}
shape = (len(SESS),) + tuple(len(v) for v in AX.values())
cube = np.full(shape, np.nan)
pos = tuple(G[k].map(idx[k]).to_numpy() for k in AX)
si = G.sess.map({s: i for i, s in enumerate(SESS)}).to_numpy()
cube[(si,) + pos] = G.R_res.to_numpy()
filled = np.where(np.isfinite(cube), cube, np.nanmean(cube))
nb = np.stack([uniform_filter(filled[k], size=3, mode="nearest") for k in range(len(SESS))])
G["nbhd"] = nb[(si,) + pos]

top = G.sort_values("R_res", ascending=False).iloc[0]
rob = G.sort_values("nbhd", ascending=False).iloc[0]
print("\n  TOP ROW by research mean R:")
print("   ", {k: (top[k] if k != "tgt" else ("none" if top[k] == 0 else f"{top[k]:g}R")) for k in
             ["sess", "ema_slow", "ema_pull", "wick", "vol", "range", "stop", "tgt"]})
print(f"    research n {int(top.n_res)} R {top.R_res:+.4f} PF {top.pf_res:.3f} ret/DD {top.rdd_res:.2f}"
      f"   neighbourhood mean {top.nbhd:+.4f}")
print("\n  NEIGHBOURHOOD-BEST cell:")
print("   ", {k: (rob[k] if k != "tgt" else ("none" if rob[k] == 0 else f"{rob[k]:g}R")) for k in
             ["sess", "ema_slow", "ema_pull", "wick", "vol", "range", "stop", "tgt"]})
print(f"    research n {int(rob.n_res)} R {rob.R_res:+.4f} PF {rob.pf_res:.3f} ret/DD {rob.rdd_res:.2f}"
      f"   neighbourhood mean {rob.nbhd:+.4f}")
print(f"\n  the top row is beaten by {100*(G.nbhd>top.nbhd).mean():.1f}% of the grid on NEIGHBOURHOOD mean")

# ---- transfer of the research ranking
for k in (100, 1000):
    t = G.sort_values("R_res", ascending=False).head(k)
    print(f"  top {k:>4} research cells: research mean {t.R_res.mean():+.4f} -> locked {t.R_lock.mean():+.4f}"
          f"   ({100*(t.R_lock>0).mean():.0f}% locked-positive, population {100*(G.R_lock>0).mean():.0f}%)")

print("\n" + "=" * 112)
print("ONE LOCKED READ of both cells, each against a matched random entry")
print("=" * 112)
print(f"  MULTIPLICITY: 108,000 sweep cells + 3,660 earlier looks = 111,660.\n")
DS = {s: V.build(sess=s) for s in SESS}


def cfg_of(row):
    return dict(sess=row.sess, p={"ema_slow": int(row.ema_slow), "ema_pull": int(row.ema_pull),
                                  "ema_tight": 20, "atr_len": 14, "atr_stop": float(row.stop),
                                  "vol_mult": float(row.vol), "range_mult": float(row["range"]),
                                  "wick_body": float(row.wick), "ambig": V.PARAMS["ambig"],
                                  "tighten_R": V.PARAMS["tighten_R"]},
                tgt_R=float(row.tgt), side=1, flatten=False)


def run_cfg(cfg, blk):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=1, p=cfg["p"])
    t = V.run(D, sig, side=1, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t[t.blk == blk].reset_index(drop=True)


def control(cfg, n_target, blk, draws=400):
    D = DS[cfg["sess"]]
    ii = np.flatnonzero((D["blk"] == blk) & D["rth"])
    rate = min(1.0, n_target / max(len(ii), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool); g[ii[RNG.random(len(ii)) < rate]] = True
        t = V.run(D, g, side=1, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
        t = t[t.blk == blk]
        if len(t) >= 20:
            out.append(t.R.mean())
    return np.array(out)


rows = []
for nm, row in (("TOP ROW", top), ("NEIGHBOURHOOD-BEST", rob)):
    cfg = cfg_of(row)
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        t = run_cfg(cfg, blk); st = V.stats(t)
        ctl = control(cfg, st["n"], blk)
        r = t.R.to_numpy(); days = t.date.to_numpy(); ud = np.unique(days)
        by = {d: r[days == d] for d in ud}
        bs = np.array([np.concatenate([by[d] for d in RNG.choice(ud, len(ud), True)]).mean()
                       for _ in range(2000)])
        y25 = t[pd.DatetimeIndex(t.ts).year >= 2025].R.sum()
        rows.append(dict(cell=nm, block=bn, n=st["n"], R=st["R"], totR=st["totR"], pf=st["pf"],
                         win=st["win"], ret_dd=st["ret_dd"], ctl_R=float(np.median(ctl)),
                         p_ctl=float((ctl >= st["R"]).mean()), boot_p=float((bs <= 0).mean()),
                         share_2025=100*y25/max(abs(st["totR"]), 1e-9)))
L = pd.DataFrame(rows)
print(L.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
for nm in ("TOP ROW", "NEIGHBOURHOOD-BEST"):
    a = L[L.cell == nm]
    rr, ll = a[a.block == "research"].iloc[0], a[a.block == "LOCKED"].iloc[0]
    print(f"  {nm:20s} research {rr.R:+.4f} -> locked {ll.R:+.4f}  "
          f"({'decays (right shape)' if ll.R < rr.R else 'GROWS on locked -- WRONG SHAPE'})"
          f"   bootstrap P(mean<=0) {ll.boot_p:.3f}   2025-26 share {ll.share_2025:.0f}%")
L.to_csv("results/vwapema/sweep_locked.csv", index=False)
G.to_parquet("results/vwapema/sweep100k.parquet")
json.dump({"top": cfg_of(top), "robust": cfg_of(rob)}, open("results/vwapema/sweep_cells.json", "w"),
          indent=1, default=float)
