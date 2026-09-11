"""STAGE 1 -- does the trigger have anything, before any condition is added?

Order matters and this branch has paid for getting it wrong. Two things run BEFORE any grid:

  1. BASE RATES ON THE TRIGGER'S OWN BARS. Five separate studies here (RSI>=55 at 94.7%,
     Aroon osc>=0 at 100.0%, MACD>0 at 99.8-100.0%, MFI>=50 at 91.7%, EMA13>48 at 90.9% of
     BREAKOUT bars) found the proposed confirmation was the trigger restated. The same query
     is two lines and it decides whether a condition can bind at all.
  2. THE TRIGGER AGAINST A RANDOM ENTRY WITH THE SAME GEOMETRY. `STUDY_TURTLE` and
     `STUDY_TURTLE_YOUTUBE` both found the exits, not the entry, were the asset. If the
     stochastic cross earns nothing over a coin flip with the same stop, target and hold,
     no VWAP or ATR condition can rescue it and this study is one file long.

RESEARCH BLOCK ONLY. Nothing here reads `blk == 1`.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vstoch as V

RNG = np.random.default_rng(20260906)
pd.set_option("display.width", 200)


def res(t):
    return t[t.blk == 0]


def control_random(D, n_target, side, stop, tp, hold, eligible, draws=400):
    """Random entries drawn from the ELIGIBLE bars at the rate n_target/len(eligible bars),
    the same geometry, and re-simulated end to end so the position lock applies identically.
    `STUDY_V42`: the rate must be n_target / ELIGIBLE bars, not / all bars."""
    idx = np.flatnonzero(eligible)
    if len(idx) == 0 or n_target == 0:
        return np.array([]), np.array([])
    rate = min(1.0, n_target / len(idx))
    means, tots = [], []
    for _ in range(draws):
        g = np.zeros(D["n"], bool)
        pick = idx[RNG.random(len(idx)) < rate]
        g[pick] = True
        t = res(V.run(D, g, side=side, stop=stop, tp=tp, hold=hold))
        if len(t) < 10:
            continue
        means.append(t.pct.mean()); tots.append(t.pct.sum())
    return np.array(means), np.array(tots)


def pval(obs, null):
    return float((null >= obs).mean()) if len(null) else np.nan


print(__doc__)
MK, TF = "NQ", 15
D = V.build(MK, TF)
print(f"  {MK} {TF}m -- {D['n']:,} bars, research/locked cut at day {D['cut_day']}, "
      f"{int((D['blk']==0).sum()):,} research bars")

lo, sh, K, Dv = V.triggers(D)
r = D["blk"] == 0
print(f"  triggers on the research block: long {int((lo&r).sum())}, short {int((sh&r).sum())}")

# ------------------------------------------------------------------ 1. base rates
print("\n" + "=" * 110)
print("BASE RATES ON THE TRIGGER'S OWN BARS -- can a condition bind at all?")
print("=" * 110)
print("  A condition passing ~100% of signal bars is the trigger restated and removes nothing.")
print("  A LIFT far from 1.0 means the condition is genuinely selecting; a lift near 1.0 with a")
print("  high pass rate means it is decoration. Measured on RESEARCH bars only.\n")

fin = np.isfinite(D["vwap"]) & np.isfinite(D["atr_ratio50"]) & np.isfinite(D["atr_pct_rank"])
pop = r & fin & D["rth"]
conds = {
    "close > VWAP (state)":            D["c"] > D["vwap"],
    "close < VWAP (state)":            D["c"] < D["vwap"],
    "VWAP rising (slope>0)":           D["vwap_slope"] > 0,
    "VWAP falling (slope<0)":          D["vwap_slope"] < 0,
    "close > VWAP AND rising":         (D["c"] > D["vwap"]) & (D["vwap_slope"] > 0),
    "|dist to VWAP| <= 0.5 ATR":       np.abs(D["vwap_dist"]) <= 0.5,
    "|dist to VWAP| >= 1.5 ATR":       np.abs(D["vwap_dist"]) >= 1.5,
    "close > VWAP_unweighted":         D["c"] > D["vwap_uw"],
    "ATR/mean50 >= 1.0 (floor)":       D["atr_ratio50"] >= 1.0,
    "ATR/mean50 >= 1.2 (floor)":       D["atr_ratio50"] >= 1.2,
    "ATR/mean50 <= 1.0 (ceiling)":     D["atr_ratio50"] <= 1.0,
    "ATR/mean50 <= 0.8 (ceiling)":     D["atr_ratio50"] <= 0.8,
    "ATR pct-rank250 >= 0.6":          D["atr_pct_rank"] >= 0.6,
    "ATR pct-rank250 <= 0.4":          D["atr_pct_rank"] <= 0.4,
}
rows = []
for nm, m in conds.items():
    m = np.nan_to_num(m, nan=False).astype(bool)
    for side_nm, trg in (("LONG", lo), ("SHORT", sh)):
        s = trg & pop
        if s.sum() == 0:
            continue
        pr = float(m[s].mean())
        gen = float(m[pop].mean())
        rows.append(dict(condition=nm, side=side_nm, pass_pct=100 * pr,
                         general_pct=100 * gen, lift=pr / max(gen, 1e-9)))
B = pd.DataFrame(rows)
for side_nm in ("LONG", "SHORT"):
    x = B[B.side == side_nm].drop(columns="side")
    print(f"  --- {side_nm} triggers (n={int((lo if side_nm=='LONG' else sh)[pop].sum())}) ---")
    print(x.to_string(index=False, float_format=lambda v: f"{v:7.2f}"))
    print()
inert = B[(B.pass_pct >= 95) | (B.pass_pct <= 5)]
print(f"  conditions that are inert on the trigger's own bars (pass >=95% or <=5%): {len(inert)} of {len(B)}")
if len(inert):
    print("   ", ", ".join(f"{a} [{b}] {c:.1f}%" for a, b, c in
                           zip(inert.condition, inert.side, inert.pass_pct)))

# ------------------------------------------------------------------ 2. trigger vs random entry
print("\n" + "=" * 110)
print("THE UNFILTERED TRIGGER AGAINST A RANDOM ENTRY WITH THE SAME GEOMETRY")
print("=" * 110)
print("  Same side, same ATR stop, same target, same hold cap, same costs, same position lock;")
print("  only the entry BAR is random, drawn from the eligible population at the same rate.")
print("  If the cross earns nothing here, no condition added later can be the reason it works.\n")

GEOM = [(2.0, 0.0, 96), (2.0, 2.0, 96), (1.5, 1.5, 48), (3.0, 0.0, 192)]
rows = []
for side_nm, trg, s in (("LONG", lo, 1), ("SHORT", sh, -1)):
    elig = r & D["rth"] & np.isfinite(D["atr"])
    for stop, tp, hold in GEOM:
        t = res(V.run(D, trg & D["rth"], side=s, stop=stop, tp=tp, hold=hold))
        st = V.stats(t)
        cm, ct = control_random(D, st["n"], s, stop, tp, hold, elig, draws=300)
        rows.append(dict(side=side_nm, stop=stop, tp=tp, hold=hold, n=st["n"],
                         pct=st["pct"], pf=st["pf"], win=st["win"], tot=st["tot"],
                         ctl_pct=float(np.median(cm)) if len(cm) else np.nan,
                         p_pct=pval(st["pct"], cm), p_tot=pval(st["tot"], ct)))
T = pd.DataFrame(rows)
print(T.to_string(index=False, float_format=lambda v: f"{v:8.4f}"))
print(f"\n  cells beating the random entry at p<=0.05 on %/trade: "
      f"{int((T.p_pct<=0.05).sum())} of {len(T)}  (expected by chance {0.05*len(T):.1f})")

os.makedirs("results/vstoch", exist_ok=True)
B.to_csv("results/vstoch/baserates.csv", index=False)
T.to_csv("results/vstoch/trigger_vs_random.csv", index=False)
