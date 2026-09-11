"""STAGE 2 -- the declared grid, on the RESEARCH block only, read by MARGINAL AVERAGE.

Axes are declared here in full before the run, so the cell count is honest and the multiplicity is
countable. `STUDY_V11_MARKET`: read a grid by its marginal average per axis, never by its top cell,
because the top cell is the maximum of N draws. `STUDY_V14_WINDOW_GRID`: report the SHARE OF THE
GRID that is profitable before reporting its top row.

The ATR family uses the CAUSAL TIME-OF-DAY baseline, not a plain trailing mean -- stage 1 measured
the plain version clearing its own threshold on 98.9% of RTH bars, which makes it a clock and not a
volatility reading.
"""
import os, sys, itertools
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vstoch as V

pd.set_option("display.width", 220)
MK, TF = "NQ", 15
D = V.build(MK, TF)
r = D["blk"] == 0

STOCH = [(14, 3, 3), (9, 3, 3), (21, 3, 3)]
LVL = [(20.0, 80.0), (15.0, 85.0), (30.0, 70.0)]
STOPS = [1.5, 2.0, 3.0]
TPS = [0.0, 1.5, 2.0, 3.0]
HOLDS = [48, 96, 192]


def vwap_masks(D, side):
    s = D["c"] - D["vwap"]
    su = D["c"] - D["vwap_uw"]
    sl = D["vwap_slope"]
    dist = np.abs(D["vwap_dist"])
    sgn = 1.0 if side > 0 else -1.0
    return {
        "off":            np.ones(D["n"], bool),
        "with_reversion": (sgn * s < 0),         # long below VWAP / short above  (fade to the mean)
        "with_trend":     (sgn * s > 0),         # long above VWAP / short below  (V63's state form)
        "anchor_trend":   (sgn * sl > 0),        # anchor sloping the trade's way
        "far>=1.0ATR":    (dist >= 1.0),
        "near<=0.5ATR":   (dist <= 0.5),
        "unweighted_rev": (sgn * su < 0),        # the volume-free twin of `with_reversion`
    }


def atr_masks(D):
    a = D["atr_ratio_tod"]; k = D["atr_tod_rank"]
    return {
        "off":        np.ones(D["n"], bool),
        "floor>=1.0": a >= 1.0,
        "floor>=1.2": a >= 1.2,
        "ceil<=1.0":  a <= 1.0,
        "ceil<=0.8":  a <= 0.8,
        "rank>=0.6":  k >= 0.6,
        "rank<=0.4":  k <= 0.4,
    }


AM = atr_masks(D)
rows = []
for (kk, dd, sm) in STOCH:
    for (osl, obl) in LVL:
        lo, sh, _, _ = V.triggers(D, kk, dd, sm, osl, obl)
        for side_nm, trg, s in (("LONG", lo, 1), ("SHORT", sh, -1)):
            VM = vwap_masks(D, s)
            for vnm, vm in VM.items():
                for anm, am in AM.items():
                    g = (trg & D["rth"]
                         & np.nan_to_num(vm, nan=False).astype(bool)
                         & np.nan_to_num(am, nan=False).astype(bool))
                    if g.sum() < 30:
                        continue
                    for stop, tp, hold in itertools.product(STOPS, TPS, HOLDS):
                        t = V.run(D, g, side=s, stop=stop, tp=tp, hold=hold)
                        t = t[t.blk == 0]
                        if len(t) < 40:
                            continue
                        st = V.stats(t)
                        rows.append(dict(side=side_nm, stoch=f"{kk}/{dd}/{sm}", lvl=osl,
                                         vwap=vnm, atr=anm, stop=stop, tp=tp, hold=hold,
                                         **st))
G = pd.DataFrame(rows)
os.makedirs("results/vstoch", exist_ok=True)
G.to_parquet("results/vstoch/grid_research.parquet")

print(__doc__)
nominal = len(STOCH) * len(LVL) * 2 * 7 * 7 * len(STOPS) * len(TPS) * len(HOLDS)
print(f"  declared cells {nominal:,};  scorable at >=40 research trades {len(G):,}")
print(f"  share of the SCORABLE grid profitable on research: {100*(G.pct>0).mean():.1f}%")
print(f"  a top row here is therefore the maximum of ~{int((G.pct>0).sum()):,} positive draws\n")

print("=" * 118)
print("MARGINAL AVERAGE PER AXIS -- what a setting does across everything else")
print("=" * 118)
for ax in ("side", "stoch", "lvl", "vwap", "atr", "stop", "tp", "hold"):
    m = G.groupby(ax).agg(n_cells=("pct", "size"), mean_pct=("pct", "mean"),
                          mean_pf=("pf", "mean"), share_pos=("pct", lambda x: 100 * (x > 0).mean()),
                          mean_trades=("n", "mean"))
    print(f"\n  --- {ax} ---")
    print(m.to_string(float_format=lambda v: f"{v:9.4f}"))

print("\n" + "=" * 118)
print("THE SIDE SPLIT, because a mean-reversion trigger is supposed to be symmetric")
print("=" * 118)
piv = G.pivot_table(index="vwap", columns="side", values="pct", aggfunc="mean")
print(piv.to_string(float_format=lambda v: f"{v:9.4f}"))
