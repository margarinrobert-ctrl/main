"""V50 post-mortem: the ENTRY GAP a market order pays, measured directly and with no limit order
anywhere in it. If PRICE rises with immediacy because the next bar's open has already moved, then
the gap itself must carry the same gradient -- and it is a cost every market-entry backtest on this
branch is already paying."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
from scipy import stats

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle"); sys.path.insert(0, "research/v50")
import v50sel as M                                        # noqa: E402
from run_v50 import load, STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, SPLIT   # noqa: E402

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
        f0, R0, Rk0, _ = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa, 0.0, 0,
                                STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, side, M.COST_PTS, M.SLIP_PTS)
        v = f0.astype(bool) & np.isfinite(R0) & (i2 < cut)
        if v.sum() < 150:
            continue
        gap_atr = side * (d1["o"][e2] - sc) / aa                 # adverse gap is POSITIVE
        rows.append(dict(family=f"{name}.{slab}", side=slab, n=int(v.sum()),
                         immed=float(np.nanmean(Rk0[v])), mkt=float(R0[v].mean()),
                         gap_atr=float(np.nanmean(gap_atr[v])),
                         gap_R=float(np.nanmean(gap_atr[v])) / STOP_MULT))
D = pd.DataFrame(rows)
D.to_csv("results/v50/v50_gap.csv", index=False)
rho = stats.spearmanr(D.immed, D.gap_atr).statistic
rng = np.random.default_rng(11)
a, b = D.immed.to_numpy(), D.gap_atr.to_numpy()
dr = np.array([stats.spearmanr(rng.permutation(a), b).statistic for _ in range(5000)])
print("=" * 100)
print("  THE CHASING COST, measured with no limit order in it at all")
print("=" * 100)
print(f"  {len(D)} family-side cells, research block")
print(f"  rho(immediacy, adverse open gap in ATR) = {rho:+.4f}   "
      f"two-sided permutation p {float(np.mean(np.abs(dr) >= abs(rho))):.4f}")
print(f"  gap  mean {D.gap_atr.mean():+.4f} ATR = {D.gap_R.mean():+.4f} R at a {STOP_MULT}N stop; "
      f"range {D.gap_atr.min():+.4f}..{D.gap_atr.max():+.4f} ATR")
q = D.assign(qq=pd.qcut(D.immed, 5, labels=False, duplicates="drop"))
g = q.groupby("qq").agg(n=("family", "size"), immed=("immed", "mean"),
                        gap=("gap_atr", "mean"), gapR=("gap_R", "mean"), mkt=("mkt", "mean"))
for k, r in g.iterrows():
    print(f"    Q{int(k)+1}  cells {int(r.n):>3}  immediacy {r.immed:+.4f}   "
          f"adverse gap {r.gap:+.4f} ATR = {r.gapR:+.4f} R   market R {r.mkt:+.4f}")
sh = D.sort_values("gap_atr")
print("\n  worst chasing cost:")
for _, x in sh.tail(5).iterrows():
    print(f"    {x.family:<18} gap {x.gap_atr:+.4f} ATR = {x.gap_R:+.4f} R   "
          f"market R {x.mkt:+.4f}   immediacy {x.immed:+.4f}")


# ---- PRICE decomposed: the pure entry offset vs the exit path -----------------------------------
from run_v50 import calibrate, LIM_MULT, MIN_FILLS                    # noqa: E402
net = pd.read_csv("results/v50/v50_net.csv").set_index("family")
rows2 = []
for name, idx in sorted(S.items()):
    for side, slab in ((1, "L"), (-1, "S")):
        fam = f"{name}.{slab}"
        if fam not in net.index or not np.isfinite(net.loc[fam, "c1_price"]):
            continue
        ent1 = m1[idx + 1]; ok = np.isfinite(ent1)
        i2, e2 = idx[ok], ent1[ok].astype(np.int64)
        sc, aa = P["c"][i2], P["atr"][i2]
        E = int(net.loc[fam, "expiry"])
        f1, _, _, _ = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa, LIM_MULT, E,
                             STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN, side, M.COST_PTS, M.SLIP_PTS)
        b = f1.astype(bool) & (i2 < cut)
        if b.sum() < MIN_FILLS:
            continue
        mkt_px = d1["o"][e2] + side * M.SLIP_PTS
        lim_px = sc - side * LIM_MULT * aa + side * M.SLIP_PTS
        offset = float(np.nanmean(side * (mkt_px - lim_px)[b] / (STOP_MULT * aa[b])))
        rows2.append(dict(family=fam, offset=offset, price=float(net.loc[fam, "c1_price"]),
                          exitpath=float(net.loc[fam, "c1_price"]) - offset,
                          immed=float(net.loc[fam, "c1_immed"])))
G = pd.DataFrame(rows2)
G.to_csv("results/v50/v50_price_split.csv", index=False)
print("\n" + "=" * 100)
print("  PRICE DECOMPOSED -- pure entry offset (an identity) vs the EXIT PATH")
print("=" * 100)
print(f"  entry offset  mean {G.offset.mean():+.6f}  sd {G.offset.std():.6f}   "
      f"(construction says {LIM_MULT/STOP_MULT:.4f})")
print(f"  exit path     mean {G.exitpath.mean():+.4f}  sd {G.exitpath.std():.4f}  "
      f"range {G.exitpath.min():+.4f}..{G.exitpath.max():+.4f}")
print(f"  share of PRICE's cross-family variance that is exit path: "
      f"{100 * G.exitpath.var() / G.price.var():.1f}%")
print(f"  rho(immediacy, exit path) = {stats.spearmanr(G.immed, G.exitpath).statistic:+.4f}")
