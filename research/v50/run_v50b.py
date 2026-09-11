"""V50 gates 3-5: the population, the NET mechanic at a matched fill rate, and the cost stress.

The calibrated expiry is COST-INVARIANT (fill_delays never sees a cost), so the same expiry is used
at every cost multiple and only the R values move.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
from scipy import stats

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle"); sys.path.insert(0, "research/v50")
import data as TD          # noqa: E402
import v50sel as M         # noqa: E402
from run_v50 import load, calibrate, LIM_MULT, STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, SPLIT, MIN_FILLS  # noqa: E402

COST_MULTS = (1.0, 1.5, 2.0)

P, d1, m1 = load()
cut = int(P["n"] * SPLIT)
S = M.signals(P)
rows = []
for name, idx in sorted(S.items()):
    for side, slab in ((1, "L"), (-1, "S")):
        ent1 = m1[idx + 1]
        ok = np.isfinite(ent1)
        i2, e2 = idx[ok], ent1[ok].astype(np.int64)
        sc, aa = P["c"][i2], P["atr"][i2]
        dly = M.fill_delays(d1["h"], d1["l"], e2, sc, aa, LIM_MULT, side, M.DELAY_CAP)
        f0b, R0b, _, _ = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa, 0.0, 0,
                                STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, side, M.COST_PTS, M.SLIP_PTS)
        valid = f0b.astype(bool) & np.isfinite(R0b)
        res = i2 < cut
        E, fach = calibrate(dly, res, valid)
        if E < 0:
            continue
        rec = {"family": f"{name}.{slab}", "side": slab, "expiry": E, "fill_res": fach}
        for cm in COST_MULTS:
            cost, slip = M.COST_PTS * cm, M.SLIP_PTS * cm
            f0, R0, Rk0, _ = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa, 0.0, 0,
                                    STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, side, cost, slip)
            f1, R1, _, _ = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa, LIM_MULT, E,
                                  STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, side, cost, slip)
            v = f0.astype(bool) & np.isfinite(R0)
            fm = f1.astype(bool) & np.isfinite(R1)
            a, b = res & v, res & v & fm
            if a.sum() < 150 or b.sum() < MIN_FILLS:
                continue
            tag = f"c{cm:g}"
            rec[f"{tag}_immed"] = float(np.nanmean(Rk0[a]))
            rec[f"{tag}_sel"] = float(R0[b].mean() - R0[a].mean())
            rec[f"{tag}_mkt"] = float(R0[a].mean())
            rec[f"{tag}_lim"] = float(R1[res & fm].mean())
            rec[f"{tag}_price"] = float(R1[res & fm].mean() - R0[b].mean())
            rec[f"{tag}_delta"] = rec[f"{tag}_lim"] - rec[f"{tag}_mkt"]
        rows.append(rec)
D = pd.DataFrame(rows)
D.to_csv("results/v50/v50_net.csv", index=False)

D = D.dropna(subset=["c1_delta", "c1_immed"])
print("=" * 100)
print("  GATE 3 -- THE POPULATION, before any cell is named")
print("=" * 100)
print(f"  {len(D)} family-side cells, fill rate {D.fill_res.min():.3f}-{D.fill_res.max():.3f}")
for cm in COST_MULTS:
    t = f"c{cm:g}"
    print(f"  cost x{cm:<4} limit beats market in {int((D[t+'_delta']>0).sum()):>3}/{len(D)} cells "
          f"({100*(D[t+'_delta']>0).mean():4.1f}%)   mean delta {D[t+'_delta'].mean():+.4f}   "
          f"SELECTION {D[t+'_sel'].mean():+.4f}   PRICE {D[t+'_price'].mean():+.4f}")
print(f"\n  PRICE as an arithmetic identity: limit depth / stop = {LIM_MULT}/{STOP_MULT} = "
      f"{LIM_MULT/STOP_MULT:.3f} R;  measured {D.c1_price.mean():+.4f}")
print(f"  rho(expiry, SELECTION) [second confound check] = "
      f"{stats.spearmanr(D.expiry, D.c1_sel).statistic:+.4f}")

print("\n" + "=" * 100)
print("  THE ZERO-CROSSING V49 COULD NOT FIND -- net delta by immediacy quintile, matched fill")
print("=" * 100)
q = D.assign(qq=pd.qcut(D.c1_immed, 5, labels=False, duplicates="drop"))
g = q.groupby("qq").agg(n=("family", "size"), immed=("c1_immed", "mean"), sel=("c1_sel", "mean"),
                        price=("c1_price", "mean"), delta=("c1_delta", "mean"),
                        pos=("c1_delta", lambda s: float((s > 0).mean())))
for k, row in g.iterrows():
    print(f"    Q{int(k)+1}  cells {int(row.n):>3}  immediacy {row.immed:+.4f}   "
          f"SELECTION {row.sel:+.4f}  PRICE {row.price:+.4f}  NET {row.delta:+.4f}  "
          f"net>0 in {100*row.pos:4.1f}%")

print("\n" + "=" * 100)
print("  GATE 4 -- COST STRESS on the gradient itself")
print("=" * 100)
for cm in COST_MULTS:
    t = f"c{cm:g}"
    rho = stats.spearmanr(D[t+"_immed"], D[t+"_sel"]).statistic
    rho_d = stats.spearmanr(D[t+"_immed"], D[t+"_delta"]).statistic
    print(f"  cost x{cm:<4} rho(immediacy, SELECTION) {rho:+.4f}   "
          f"rho(immediacy, NET delta) {rho_d:+.4f}")
