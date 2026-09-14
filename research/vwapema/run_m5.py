"""M5 -- the always-in control and the regime split, on US100, US30 and the reserved US30_ISO.

Two questions, in this order, because the second is only interesting if the first is answered:

  1. IS THE RULE A BETTER WAY OF BEING IN THE MARKET THAN SIMPLY BEING IN IT?  On the SAME
     qualifying days, same side, enter at the session open and carry the RULE'S OWN ATR STOP, so
     the control cannot be accused of taking more risk. This is the test that settled the gold
     study (`STUDY_VWAP_EMA_GOLD` section 32: the rule lost in 11 of 12 preset-blocks).

  2. LONG vs SHORT in BULL vs BEAR.  The regime label is CAUSAL: the daily close against its own
     200-day EMA, LAGGED one session, forward-filled onto the 15-minute bars, so a bar at 10:00 on
     session D reads the state as of the close of D-1. One parameter (200), taken as the
     conventional value and never swept. Applied as a FILTER and RE-SIMULATED, never as a split of
     the realised trades -- refusing a signal frees the position lock and admits a later one
     (STUDY_AUCTION), so the two readings answer different questions.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

pd.set_option("display.width", 235)
print(__doc__)
MK = ("US100", "US30", "US30_ISO")
DS = {(k, sm): M.build(k, sess=sm) for k in MK for sm in ("ny", "utc")}
FN = pd.read_csv("results/vwapema/m2_finalists.csv")
PKEYS = list(V.PARAMS)
L = lambda s: print("\n" + "=" * 118 + f"\n{s}\n" + "=" * 118)


def cfg_of(row):
    p = {k: (int(row[k]) if isinstance(V.PARAMS[k], int) else float(row[k])) for k in PKEYS}
    tg = row.get("tgt_R", 0.0)
    if not row.get("use_tgt", True) or not np.isfinite(float(tg)):
        tg = 0.0
    return dict(p=p, side=int(row["side"]), sess=str(row["sess"]), tgt_R=float(tg),
                flatten=bool(row["flatten"]))


CELLS = {"As published L": dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False),
         "As published S": dict(p=dict(V.PARAMS), side=-1, sess="ny", tgt_R=3.0, flatten=False)}
for _, r in FN.iterrows():
    CELLS[f"{r.feed} Optuna {r.study}"] = cfg_of(r)


def regime(D, n=200):
    """+1 bull / -1 bear from the daily close against its own 200-day EMA, LAGGED one session."""
    c = pd.Series(D["c"], index=pd.DatetimeIndex(D["ix"]))
    dc = c.resample("D").last().dropna()
    e = dc.ewm(span=n, adjust=False).mean()
    s = pd.Series(np.where(dc > e, 1, -1), index=dc.index).shift(1)
    return s.reindex(pd.DatetimeIndex(D["ix"]).normalize()).ffill().to_numpy()


REG = {(k, sm): regime(DS[(k, sm)]) for (k, sm) in DS}


def run_side(mk, cfg, side, reg_filter=None):
    """RESTRICT the signal to one regime and RE-SIMULATE. Not a split of realised trades: a refused
    signal frees the position lock and admits a later one the unrestricted run never saw."""
    D = DS[(mk, cfg["sess"])]
    g = REG[(mk, cfg["sess"])]
    sig, _ = V.triggers(D, side=side, p=cfg["p"])
    if reg_filter is not None:
        sig = sig & (g == reg_filter)
    t = M.run(D, sig, side=side, tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    t["reg"] = g[t.sig.to_numpy()]
    return t


def always_in(mk, cfg, t, side):
    """Same DAYS the rule traded, same side, entry at the FIRST New York bar of the day, carrying
    the rule's own ATR stop and the same target/trail. Not more risk, just no entry conditions."""
    D = DS[(mk, cfg["sess"])]
    if len(t) == 0:
        return t
    days = set(pd.DatetimeIndex(t.date).values.astype("datetime64[D]").astype(np.int64))
    first = np.zeros(D["n"], bool)
    seen = set()
    idx = np.flatnonzero(D["rth"])
    for i in idx:
        d = D["day"][i]
        if d in days and d not in seen:
            first[i] = True
            seen.add(d)
    a = M.run(D, first, side=side, tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    return a


L("M5.1  REGIME MIX per feed and block -- the two blocks are not the same market")
rows = []
for mk in MK:
    D = DS[(mk, "ny")]; g = REG[(mk, "ny")]
    for b, bn in ((0, "research"), (1, "LOCKED")):
        m = D["rth"] & (D["blk"] == b)
        c = D["c"][m]
        rows.append(dict(feed=mk, block=bn, bars=int(m.sum()),
                         bull_pct=round(100 * float((g[m] > 0).mean()), 1),
                         index_move_pct=round(100 * (c[-1] / c[0] - 1), 1)))
    m = D["rth"]
    rows.append(dict(feed=mk, block="whole", bars=int(m.sum()),
                     bull_pct=round(100 * float((g[m] > 0).mean()), 1),
                     index_move_pct=round(100 * (D["c"][m][-1] / D["c"][m][0] - 1), 1)))
G = pd.DataFrame(rows)
print(G.to_string(index=False))
G.to_csv("results/vwapema/m5_regime_mix.csv", index=False)

L("M5.2  THE REGIME FILTER, RE-SIMULATED -- long and short, bull only / both / bear only")
rows = []
for mk in MK:
    for nm, cfg in CELLS.items():
        for side, sn in ((1, "LONG"), (-1, "SHORT")):
            for flt, fn in ((None, "both regimes"), (1, "bull only"), (-1, "bear only")):
                t = run_side(mk, cfg, side, flt)
                for b, bn in ((0, "research"), (1, "LOCKED")):
                    st = V.stats(t[t.blk == b])
                    if st["n"] < 12:
                        continue
                    rows.append(dict(feed=mk, cell=nm, side=sn, filter=fn, block=bn,
                                     n=st["n"], R=round(st["R"], 4), pct=round(st["pct"], 4),
                                     pf=round(st["pf"], 3), win=round(st["win"], 1)))
F2 = pd.DataFrame(rows)
F2.to_csv("results/vwapema/m5_regime_filter.csv", index=False)
for mk in MK:
    for side in ("LONG", "SHORT"):
        s = F2[(F2.feed == mk) & (F2.side == side) & (F2.block == "LOCKED")]
        if len(s) == 0:
            continue
        print(f"\n--- {mk}  {side}  LOCKED (R per trade)")
        print(s.pivot(index="cell", columns="filter", values="R").to_string())

L("M5.3  DOES THE BULL FILTER HELP?  Counted over every cell, both blocks, both sides")
rows = []
for mk in MK:
    for side in ("LONG", "SHORT"):
        for b in ("research", "LOCKED"):
            s = F2[(F2.feed == mk) & (F2.side == side) & (F2.block == b)]
            p = s.pivot(index="cell", columns="filter", values="R").dropna()
            if len(p) == 0:
                continue
            rows.append(dict(feed=mk, side=side, block=b, cells=len(p),
                             bull_beats_both=int((p["bull only"] > p["both regimes"]).sum()),
                             bear_beats_both=int((p["bear only"] > p["both regimes"]).sum()),
                             positive=int((p["both regimes"] > 0).sum())))
H = pd.DataFrame(rows)
print(H.to_string(index=False))
H.to_csv("results/vwapema/m5_regime_counts.csv", index=False)

L("M5.4  THE ALWAYS-IN CONTROL -- same days, same side, same stop, entry at the session open")
rows = []
for mk in MK:
    for nm, cfg in CELLS.items():
        for side, sn in ((1, "LONG"), (-1, "SHORT")):
            for flt, fn in ((1, "bull"), (-1, "bear")):
                t = run_side(mk, cfg, side, flt)
                if len(t) < 25:
                    continue
                a = always_in(mk, cfg, t, side)
                for b, bn in ((0, "research"), (1, "LOCKED")):
                    tb, ab = t[t.blk == b], a[a.blk == b]
                    if len(tb) < 12 or len(ab) < 12:
                        continue
                    rows.append(dict(feed=mk, cell=nm, side=sn, regime=fn, block=bn,
                                     n=len(tb), R=round(tb.R.mean(), 4),
                                     always_n=len(ab), always_R=round(ab.R.mean(), 4),
                                     edge=round(tb.R.mean() - ab.R.mean(), 4)))
A = pd.DataFrame(rows)
A.to_csv("results/vwapema/m5_alwaysin.csv", index=False)
print(A.groupby(["side", "regime"]).agg(cells=("edge", "size"), mean_edge=("edge", "mean"),
                                        rule_wins=("edge", lambda s: int((s > 0).sum())),
                                        rule_R=("R", "mean"),
                                        always_R=("always_R", "mean")).round(4).to_string())
print(f"\nThe rule beats always-in in {int((A.edge > 0).sum())} of {len(A)} cells.")
print("\nby feed:")
print(A.groupby("feed").agg(cells=("edge", "size"), mean_edge=("edge", "mean"),
                            wins=("edge", lambda s: int((s > 0).sum()))).round(4).to_string())
print("\nRead the control's OWN level, not only the excess: a session-open entry with an ATR stop")
print("in a market that rose is a drift harvester and can be positive on both sides (STUDY_TURTLE).")
