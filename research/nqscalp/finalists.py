"""The only cells that survived the cheap screen, put through the whole gate.

G1 net > round turn (research)   G2 excess over matched control, p < 0.05
G3 still above the round turn with 2020+2022 removed   G4 walk-forward inside research
G5 replicates on the second instrument
"""
import numpy as np, pandas as pd, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
TM, ORD = "barclose", "adverse"
SPEC = {"NAS":  dict(point_value=20.0, tick=0.25, commission=1.24, qty=1),
        "US30": dict(point_value=5.0,  tick=1.00, commission=1.24, qty=1)}
BASE = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0,
            trail_offset_atr=0.5, sess_start_h=6, sess_start_m=0,
            sess_end_h=11, sess_end_m=30)
CAND = [("MACD momentum confirm", dict(use_macd=True)),
        ("volume 1.5x thrust", dict(use_volume=True, vol_mult=1.5)),
        ("volume 1.2x + MACD", dict(use_volume=True, vol_mult=1.2, use_macd=True))]

rows = []
for sym in ("NAS", "US30"):
    df = D.load(sym); R, H = D.blocks(df)
    RT = 2 * SPEC[sym]["tick"] + 2 * SPEC[sym]["commission"] / SPEC[sym]["point_value"]
    print(f"\n{'='*126}\n36. FINALISTS THROUGH THE FULL GATE - {sym} (round turn {RT:.2f} pts)\n{'='*126}")
    for lbl, kw in CAND:
        I, p = nqs.indicators(df, **{**SPEC[sym], **BASE, **kw})
        (lo, sh), _ = nqs.conditions(df, I, p)
        tr = nqs.simulate(df, I, p, lo & R, sh & R, order=ORD, trail_mode=TM)
        if len(tr) < 40:
            print(f"  {lbl:<24} too few trades"); continue
        g = NC.score(df, I, p, tr, n_draws=500, mask=R, order=ORD, trail_mode=TM)
        yy = pd.DatetimeIndex(tr.ts).year
        ex = tr[(yy != 2020) & (yy != 2022)]
        exv = float(ex.net_pts.mean())
        # walk-forward on this single fixed configuration - no re-selection, so it
        # is a stability test rather than a selection test
        rs = np.unique(df.sess.values[R]); folds = []
        s0, step = rs.min(), 250
        while s0 + step <= rs.max():
            m = (tr.sess.values >= s0) & (tr.sess.values < s0 + step)
            if m.sum() >= 15: folds.append(tr.net_pts.values[m].mean())
            s0 += step
        folds = np.array(folds)
        g1 = g["exp"] > RT; g2 = g["excess"] > 0 and g["p"] < 0.05
        g3 = exv > RT; g4 = len(folds) > 0 and (folds > 0).mean() >= 0.60 and np.median(folds) > 0
        rows.append(dict(sym=sym, cand=lbl, n=len(tr), net=g["exp"], ctrl=g["ctrl"],
                         excess=g["excess"], p=g["p"], ex_crisis=exv, rt=RT,
                         blocks=len(folds), blocks_pos=float((folds > 0).mean()) if len(folds) else np.nan,
                         median_block=float(np.median(folds)) if len(folds) else np.nan,
                         G1=bool(g1), G2=bool(g2), G3=bool(g3), G4=bool(g4)))
        print(f"  {lbl:<24} n={len(tr):>5} net{g['exp']:>+7.2f} ctrl{g['ctrl']:>+7.2f} "
              f"excess{g['excess']:>+7.2f} p={g['p']:.4f} ex-crisis{exv:>+7.2f}  "
              f"250-session blocks {len(folds)}, {(folds>0).mean() if len(folds) else 0:.0%} positive, "
              f"median {np.median(folds) if len(folds) else 0:+.2f}")
        print(f"  {'':<24} G1 net>RT {'PASS' if g1 else 'FAIL'}   G2 control {'PASS' if g2 else 'FAIL'}"
              f"   G3 ex-crisis {'PASS' if g3 else 'FAIL'}   G4 stability {'PASS' if g4 else 'FAIL'}")
T = pd.DataFrame(rows); T.to_csv(OUT + "finalists.csv", index=False)

print(f"\n{'='*126}\n  G5 CROSS-INSTRUMENT - a candidate must pass on BOTH\n{'='*126}")
print(f"  {'candidate':<24}{'NAS G1-G4':>14}{'US30 G1-G4':>14}{'verdict':>12}")
for lbl, _ in CAND:
    a = T[(T.sym == "NAS") & (T.cand == lbl)]
    b = T[(T.sym == "US30") & (T.cand == lbl)]
    if not len(a) or not len(b): continue
    a, b = a.iloc[0], b.iloc[0]
    an = sum([a.G1, a.G2, a.G3, a.G4]); bn = sum([b.G1, b.G2, b.G3, b.G4])
    ok = an == 4 and bn == 4
    print(f"  {lbl:<24}{f'{an}/4':>14}{f'{bn}/4':>14}{'PASS' if ok else 'FAIL':>12}")
print(f"\n  candidates passing every gate on both instruments: "
      f"{sum(1 for lbl,_ in CAND if len(T[(T.sym=='NAS')&(T.cand==lbl)]) and len(T[(T.sym=='US30')&(T.cand==lbl)]) and all([T[(T.sym=='NAS')&(T.cand==lbl)].iloc[0][g] for g in ('G1','G2','G3','G4')]) and all([T[(T.sym=='US30')&(T.cand==lbl)].iloc[0][g] for g in ('G1','G2','G3','G4')]))}")
json.dump(T.to_dict("records"), open(OUT + "finalists.json", "w"), indent=2, default=str)
