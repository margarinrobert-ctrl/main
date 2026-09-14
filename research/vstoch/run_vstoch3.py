"""STAGE 3 -- the two nulls, the neighbourhood, ONE locked read, and the cross-market read.

The candidate is the MARGINAL-CONSENSUS cell -- the best setting on each axis read across
everything else -- not the top row, which is the maximum of ~7,273 positive draws.

Two nulls, because they answer different questions and this branch has repeatedly found a rule
clearing one and failing the other (`STUDY_V61`: the incumbent clears a random FILTER and fails a
random ENTRY; the unfiltered geometry does the reverse):
  * RANDOM ENTRY, same side / stop / target / hold / costs / position lock -- is the TRIGGER worth
    anything, or is the exit geometry the asset?
  * SAME-SELECTIVITY RANDOM FILTER, keeping the same number of the unfiltered trigger's bars -- are
    the VWAP and ATR conditions worth anything, or is restrictiveness alone doing it?
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vstoch as V

RNG = np.random.default_rng(4417)
pd.set_option("display.width", 210)
G = pd.read_parquet("results/vstoch/grid_research.parquet")
print(__doc__)

# ---------------------------------------------------------------- the consensus cell
best = {}
for ax in ("side", "stoch", "lvl", "vwap", "atr", "stop", "tp", "hold"):
    m = G.groupby(ax)["pct"].mean()
    if ax == "vwap":
        m = m.drop(index=[i for i in m.index if G[G.vwap == i].shape[0] < 300])
    best[ax] = m.idxmax()
print("  MARGINAL CONSENSUS (best marginal average on each axis, read across everything else):")
for k, v in best.items():
    print(f"    {k:6s} {v}")
top = G.sort_values("pct", ascending=False).iloc[0]
print(f"\n  TOP ROW for comparison: {top.side} {top.stoch} lvl{top.lvl:.0f} {top.vwap} {top.atr} "
      f"stop{top.stop} tp{top.tp} hold{top.hold} -> {top.pct:+.4f} %/trade PF {top.pf:.3f} n {int(top.n)}")
c = G[(G.side == best["side"]) & (G.stoch == best["stoch"]) & (G.lvl == best["lvl"]) &
      (G.vwap == best["vwap"]) & (G.atr == best["atr"]) & (G.stop == best["stop"]) &
      (G.tp == best["tp"]) & (G.hold == best["hold"])]
print(f"  CONSENSUS CELL on research: {c.iloc[0].pct:+.4f} %/trade PF {c.iloc[0].pf:.3f} "
      f"n {int(c.iloc[0].n)} win {c.iloc[0].win:.1f}% ret/DD {c.iloc[0].ret_dd:.2f}")


def cell_gate(D, cfg):
    kk, dd, sm = (int(x) for x in cfg["stoch"].split("/"))
    osl = cfg["lvl"]; obl = 100.0 - osl
    lo, sh, _, _ = V.triggers(D, kk, dd, sm, osl, obl)
    s = 1 if cfg["side"] == "LONG" else -1
    trg = lo if s > 0 else sh
    sgn = 1.0 if s > 0 else -1.0
    vm = {"off": np.ones(D["n"], bool),
          "with_reversion": sgn * (D["c"] - D["vwap"]) < 0,
          "with_trend": sgn * (D["c"] - D["vwap"]) > 0,
          "anchor_trend": sgn * D["vwap_slope"] > 0,
          "far>=1.0ATR": np.abs(D["vwap_dist"]) >= 1.0,
          "near<=0.5ATR": np.abs(D["vwap_dist"]) <= 0.5,
          "unweighted_rev": sgn * (D["c"] - D["vwap_uw"]) < 0}[cfg["vwap"]]
    am = {"off": np.ones(D["n"], bool),
          "floor>=1.0": D["atr_ratio_tod"] >= 1.0, "floor>=1.2": D["atr_ratio_tod"] >= 1.2,
          "ceil<=1.0": D["atr_ratio_tod"] <= 1.0, "ceil<=0.8": D["atr_ratio_tod"] <= 0.8,
          "rank>=0.6": D["atr_tod_rank"] >= 0.6, "rank<=0.4": D["atr_tod_rank"] <= 0.4}[cfg["atr"]]
    base = trg & D["rth"]
    full = base & np.nan_to_num(vm, nan=False).astype(bool) & np.nan_to_num(am, nan=False).astype(bool)
    return base, full, s


def score(D, gate, cfg, s, blk):
    t = V.run(D, gate, side=s, stop=cfg["stop"], tp=cfg["tp"], hold=int(cfg["hold"]))
    t = t[t.blk == blk]
    return t, V.stats(t)


def null_random_entry(D, cfg, s, n_target, blk, draws=400):
    elig = np.flatnonzero(D["rth"] & np.isfinite(D["atr"]) & (D["blk"] == blk))
    rate = min(1.0, n_target / max(len(elig), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool); g[elig[RNG.random(len(elig)) < rate]] = True
        t, st = score(D, g, cfg, s, blk)
        if st["n"] >= 10:
            out.append(st["pct"])
    return np.array(out)


def null_random_filter(D, base, cfg, s, keep, blk, draws=400):
    idx = np.flatnonzero(base & (D["blk"] == blk))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool)
        g[RNG.choice(idx, size=min(keep, len(idx)), replace=False)] = True
        t, st = score(D, g, cfg, s, blk)
        if st["n"] >= 10:
            out.append(st["pct"])
    return np.array(out)


cfg = dict(best); cfg["lvl"] = float(best["lvl"])
print("\n" + "=" * 118)
print("THE TWO NULLS ON RESEARCH")
print("=" * 118)
D = V.build("NQ", 15)
base, full, s = cell_gate(D, cfg)
tR, stR = score(D, full, cfg, s, 0)
tB, stB = score(D, base, cfg, s, 0)
ne = null_random_entry(D, cfg, s, stR["n"], 0)
nf = null_random_filter(D, base, cfg, s, int((full & (D["blk"] == 0)).sum()), 0)
print(f"  unfiltered trigger (RTH, same geometry): n {stB['n']:4d}  {stB['pct']:+.4f} %/trade  PF {stB['pf']:.3f}")
print(f"  the consensus cell                     : n {stR['n']:4d}  {stR['pct']:+.4f} %/trade  PF {stR['pf']:.3f}")
print(f"  vs RANDOM ENTRY  median {np.median(ne):+.4f}   p {float((ne>=stR['pct']).mean()):.3f}")
print(f"  vs RANDOM FILTER median {np.median(nf):+.4f}   p {float((nf>=stR['pct']).mean()):.3f}")

# ---------------------------------------------------------------- neighbourhood
print("\n" + "=" * 118)
print("NEIGHBOURHOOD -- one rung on every ordered axis (a spike is an artefact, not a plateau)")
print("=" * 118)
nb = []
for ax, alts in (("stop", [1.5, 2.0, 3.0]), ("tp", [0.0, 1.5, 2.0, 3.0]),
                 ("hold", [48, 96, 192]), ("lvl", [15.0, 20.0, 30.0]),
                 ("stoch", ["9/3/3", "14/3/3", "21/3/3"])):
    for a in alts:
        q = G[(G.side == cfg["side"]) & (G.vwap == cfg["vwap"]) & (G.atr == cfg["atr"])]
        for k2 in ("stoch", "lvl", "stop", "tp", "hold"):
            q = q[q[k2] == (a if k2 == ax else cfg[k2])]
        if len(q):
            nb.append(dict(axis=ax, value=a, pct=q.iloc[0].pct, pf=q.iloc[0].pf, n=int(q.iloc[0].n)))
NB = pd.DataFrame(nb)
print(NB.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print(f"\n  neighbours profitable: {int((NB.pct>0).sum())} of {len(NB)}")

# ---------------------------------------------------------------- ONE locked read
print("\n" + "=" * 118)
print("THE ONE LOCKED READ -- declared in advance: the marginal-consensus cell, both nulls")
print("=" * 118)
print(f"  multiplicity first: 31,752 declared cells, 19,579 scorable, one cell read here.\n")
tL, stL = score(D, full, cfg, s, 1)
tBL, stBL = score(D, base, cfg, s, 1)
neL = null_random_entry(D, cfg, s, stL["n"], 1)
nfL = null_random_filter(D, base, cfg, s, int((full & (D["blk"] == 1)).sum()), 1)
print(f"  unfiltered trigger, LOCKED : n {stBL['n']:4d}  {stBL['pct']:+.4f} %/trade  PF {stBL['pf']:.3f}")
print(f"  the consensus cell, LOCKED : n {stL['n']:4d}  {stL['pct']:+.4f} %/trade  PF {stL['pf']:.3f}  "
      f"win {stL['win']:.1f}%  ret/DD {stL['ret_dd']:.2f}")
print(f"  vs RANDOM ENTRY  median {np.median(neL):+.4f}   p {float((neL>=stL['pct']).mean()):.3f}")
print(f"  vs RANDOM FILTER median {np.median(nfL):+.4f}   p {float((nfL>=stL['pct']).mean()):.3f}")
shape = "DECAYS across the split (right shape)" if stL["pct"] < stR["pct"] else \
        "GROWS on locked -- the WRONG SHAPE, seen twelve times on this branch"
print(f"  shape: research {stR['pct']:+.4f} -> locked {stL['pct']:+.4f}  ({shape})")

# ---------------------------------------------------------------- cross-market
print("\n" + "=" * 118)
print("CROSS-MARKET -- the cell FROZEN and run on two feeds that had no part in choosing it")
print("=" * 118)
rows = [dict(market="NQ", block="research", **stR), dict(market="NQ", block="locked", **stL)]
for mk in ("US100", "US30"):
    try:
        Dx = V.build(mk, 15)
    except Exception as e:
        print(f"  {mk}: unavailable ({e})"); continue
    bx, fx, sx = cell_gate(Dx, cfg)
    for blk, nm in ((0, "research"), (1, "locked")):
        t, st = score(Dx, fx, cfg, sx, blk)
        nn = null_random_entry(Dx, cfg, sx, st["n"], blk, draws=250)
        rows.append(dict(market=mk, block=nm, **st,
                         p_entry=float((nn >= st["pct"]).mean()) if len(nn) else np.nan))
X = pd.DataFrame(rows)
print(X.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
X.to_csv("results/vstoch/crossmarket.csv", index=False)
NB.to_csv("results/vstoch/neighbourhood.csv", index=False)
import json
json.dump({k: (float(v) if isinstance(v, (int, float, np.integer, np.floating)) else str(v)) for k, v in cfg.items()},
          open("results/vstoch/cell.json", "w"), indent=1)
